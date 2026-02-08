# ADR-0001: Ledger-First Balance Computation

## Status

Accepted

## Date

2025-01-01

## Context

Power PTO needs to track employee time-off balances that change through multiple events: accruals, holds (pending requests), approvals (converting holds to usage), denials/cancellations (releasing holds), admin adjustments, carryover, and expiration. The system must:

1. **Explain any balance** — given a balance of 6,720 minutes, we need to answer "how did we get here?" at any point in time
2. **Support auditability** — regulators, HR, and employees need a full trail of every change
3. **Handle policy changes gracefully** — when a policy is updated, past events should not be silently rewritten
4. **Prevent double-spend** — concurrent requests must not overdraw an employee's balance
5. **Support corrections** — admin adjustments and retroactive fixes must be traceable, not destructive mutations

Two primary approaches were considered:

### Option A: Derived Balances (Running Total)

Store only the current balance in a single row (e.g., `balance_minutes` column). Each operation directly mutates this value. History is stored separately in an audit log or event table that is not the source of truth.

**Pros:**
- Simple reads: one row per (employee, policy)
- Fewer writes per operation (one UPDATE)

**Cons:**
- Balance discrepancies are hard to debug — the audit trail is secondary, not the source of truth
- Corrections require editing the balance row directly, losing the "why"
- Rebuilding a balance at a specific point in time requires replaying audit events that may not contain enough detail
- A bug in balance update logic silently corrupts the balance with no recovery path

### Option B: Ledger-First (Append-Only Entries + Derived Snapshot)

Every balance-affecting event creates an immutable, append-only ledger entry. The current balance is a derived value computed by aggregating ledger entries. A balance snapshot table serves as a transactionally-updated cache for fast reads.

**Pros:**
- The ledger is the source of truth — any discrepancy can be debugged by replaying entries
- Full traceability: every entry has a type, source, timestamp, and metadata
- Corrections are new entries (ADJUSTMENT), not mutations
- Point-in-time balances can be reconstructed by filtering entries up to a timestamp
- Idempotency is naturally enforced via unique constraints on (source_type, source_id, entry_type)

**Cons:**
- More writes per operation (INSERT ledger entry + UPDATE snapshot)
- Balance reads require either a snapshot or an aggregation query
- Storage grows over time (one row per event per employee per policy)

## Decision

We chose **Option B: Ledger-First** with a transactionally-updated snapshot cache.

### Implementation Details

**Ledger table (`time_off_ledger_entry`):**

- Append-only — entries are never updated or deleted
- Each entry records: entry type (ACCRUAL, HOLD, HOLD_RELEASE, USAGE, ADJUSTMENT, EXPIRATION, CARRYOVER), signed amount in minutes, source type and ID, policy version reference, and metadata
- Unique constraint on `(source_type, source_id, entry_type)` provides natural idempotency

**Snapshot table (`time_off_balance_snapshot`):**

- Derived cache with composite primary key `(company_id, employee_id, policy_id)`
- Stores `accrued_minutes`, `used_minutes`, `held_minutes`, `available_minutes`
- Updated transactionally alongside every ledger write using `SELECT ... FOR UPDATE`
- Includes an optimistic locking `version` counter
- If a snapshot doesn't exist, it is computed from ledger entries and created on first access

**Balance formula:**

```
available = accrued - used - held
```

**Concurrency control:**

All balance-mutating operations lock the snapshot row with `SELECT ... FOR UPDATE` inside a single transaction, preventing double-spend under concurrent requests.

## Consequences

### Positive

- **Auditability** — every balance change has a first-class record with type, source, and metadata; no separate audit table needed for balance history
- **Debuggability** — "why is this balance wrong?" is answered by querying the ledger, not reverse-engineering mutations
- **Immutability** — past entries are never changed; corrections are explicit ADJUSTMENT entries with reasons
- **Idempotency** — the unique constraint prevents duplicate entries from retried operations (payroll events, approval clicks)
- **Point-in-time queries** — balance at any date can be reconstructed by aggregating entries up to that timestamp
- **Policy version tracking** — each entry references the policy version in effect when it was created

### Negative

- **Write amplification** — every operation requires both a ledger INSERT and a snapshot UPDATE; this is acceptable for our scale
- **Storage growth** — the ledger table grows linearly with events; for typical usage (a few entries per employee per month), this is manageable for years
- **Snapshot drift risk** — if the snapshot update fails independently of the ledger write, the snapshot could become stale; this is mitigated by performing both operations in the same transaction and providing a fallback recomputation path

### Neutral

- The snapshot is a performance optimization, not a correctness requirement — the system can always fall back to computing balances from the ledger
- Schema migrations for the ledger table must be additive (new columns, not column renames or removals)
