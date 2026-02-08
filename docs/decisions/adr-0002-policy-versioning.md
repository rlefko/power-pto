# ADR-0002: Immutable Policy Versioning

## Status

Accepted

## Date

2025-01-01

## Context

Time-off policies change over time. An admin might increase the annual accrual rate, add a bank cap, enable carryover, or switch from monthly to daily accrual. When these changes happen, the system must:

1. **Preserve history** — past balance computations, ledger entries, and accruals should reflect the rules that were in effect when they occurred
2. **Support "what policy was active on date X?" queries** — for audit, debugging, and retroactive analysis
3. **Allow future-dated changes** — an admin might create a new policy version effective January 1 of next year
4. **Remain auditable** — every change must record who made it, when, and why

Three approaches were considered:

### Option A: Mutable Policy Row

Store policy settings in a single row. Updates overwrite the row. History is captured only in an audit log's before/after snapshots.

**Pros:**
- Simple schema — one row per policy
- Easy to query "current settings"

**Cons:**
- No first-class history — requires parsing audit log JSON to reconstruct past settings
- Ledger entries have no reference to which settings were used when they were created
- Future-dated changes require a separate mechanism (e.g., a "pending changes" table)
- Retroactive queries require correlating timestamps across tables

### Option B: Temporal Table (System Versioning)

Use PostgreSQL temporal tables or a framework-level equivalent to automatically version every row change with valid-from/valid-to timestamps.

**Pros:**
- Automatic versioning without application logic
- SQL-level temporal queries

**Cons:**
- PostgreSQL temporal tables are limited compared to SQL:2011 spec
- Application-level logic for effective dating is still needed
- Tight coupling to database features that may not port to other stores
- Harder to associate specific ledger entries with specific versions

### Option C: Explicit Version Rows (Immutable Versions)

Separate the policy identity (`time_off_policy`) from its configuration (`time_off_policy_version`). Every update creates a new version row with `effective_from` and `effective_to` dates. Prior versions are never mutated.

**Pros:**
- First-class version history with clean queries
- Ledger entries can directly reference the version they were computed under (FK to `policy_version_id`)
- Future-dated versions are natural: create a version with `effective_from` in the future
- Half-open interval queries are simple: `effective_from <= date AND (effective_to IS NULL OR effective_to > date)`
- Each version is a standalone snapshot of all settings — no need to diff or reconstruct

**Cons:**
- More rows — one per version per policy (typically very few: 1–5 over a policy's lifetime)
- "Get current settings" requires a query with ordering or a filter on `effective_to IS NULL`
- Updates require both end-dating the current version and inserting a new one (two writes in one transaction)

## Decision

We chose **Option C: Explicit Version Rows** with immutable version snapshots.

### Implementation Details

**Policy table (`time_off_policy`):**

- Stable identity for a policy: `id`, `company_id`, `key`, `category`
- The `key` field (e.g., `vacation-ft`) is unique per company and never changes
- Does not contain any settings — only identity and categorization

**Version table (`time_off_policy_version`):**

- Each row is an immutable snapshot of the policy's full configuration
- Fields: `policy_id` (FK), `version` (monotonically increasing integer), `effective_from` (date), `effective_to` (date, nullable), `type`, `accrual_method`, `settings_json` (validated by Pydantic discriminated union), `created_by`, `change_reason`, `created_at`
- Unique constraint on `(policy_id, version)` prevents duplicate version numbers
- `effective_to` is `NULL` for the current (latest) version

**Update flow:**

1. Load the current version (where `effective_to IS NULL`)
2. Validate the new `effective_from` is >= the current version's `effective_from`
3. Set the current version's `effective_to` to the new version's `effective_from`
4. Insert the new version with the next version number
5. Audit both the end-dating and the creation

**Version lookup:**

- **Current version:** `WHERE effective_to IS NULL ORDER BY version DESC LIMIT 1`
- **Effective on date:** `WHERE effective_from <= date AND (effective_to IS NULL OR effective_to > date) ORDER BY version DESC LIMIT 1`

**Ledger integration:**

Every ledger entry (`time_off_ledger_entry`) includes a `policy_version_id` FK, recording exactly which version's rules were applied when the entry was created. This means accrual calculations, bank caps, and carryover rules are traceable to the specific policy configuration that was in effect.

## Consequences

### Positive

- **Complete audit trail** — every version is a preserved record with who created it, when, why, and what the settings were
- **Referential integrity** — ledger entries link to the exact version they were computed under; no ambiguity about which rules applied
- **Clean temporal queries** — "what was the policy on March 15?" is a single indexed query, not an audit log parse
- **Future-dated changes** — creating a version with `effective_from` in the future is natural and requires no special handling
- **Settings validation** — each version's `settings_json` is validated at creation time via Pydantic discriminated unions; past versions remain valid under their original schema

### Negative

- **Query complexity for "current"** — getting the current settings requires filtering on `effective_to IS NULL` rather than a simple row fetch; this is a minor overhead mitigated by indexing
- **Two-write updates** — policy updates require both an UPDATE (end-dating) and an INSERT (new version) in a single transaction; this is straightforward with proper transaction management
- **Version count grows** — each update adds a row; in practice, policies change infrequently (a few times per year at most), so this is negligible

### Neutral

- Retroactive policy changes are explicitly not supported through version mutation; they require admin ADJUSTMENT entries on affected employee balances, which aligns with the ledger-first philosophy (see [ADR-0001](adr-0001-ledger-vs-derived.md))
- The `settings_json` column uses a Pydantic discriminated union for validation, which means schema evolution for settings must be handled at the application layer (adding optional fields with defaults)
