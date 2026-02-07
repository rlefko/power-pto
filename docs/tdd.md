Technical Design Document

1. Tech stack & repo principles

Backend

- Python 3.14 target (practically: ensure compatibility with 3.13+ if base images lag)
- FastAPI
- PostgreSQL
- SQLAlchemy + SQLModel
- Alembic migrations
- Pydantic for typed schemas

Frontend

- TypeScript + React + Vite
- Component system: shadcn/ui style (Radix primitives + Tailwind) for best parity with Warp’s publicly discussed UI approach ￼
- Data fetching: TanStack Query (recommended)

DevEx / Ops

- Fully dockerized (Docker + docker-compose)
- make commands for common workflows
- GitHub Actions CI
- Docs in /docs + Mermaid diagrams in Markdown

Engineering philosophy alignment

- Ship fast, ship right; small PRs; tight loops; maximize leverage; secure by default ￼

---

2. High-level architecture

Components

- frontend: React app
- api: FastAPI application
- worker: background worker for scheduled accrual + backfills (optional in MVP; recommended for "complete")
- db: Postgres
- External (stubbed locally): Employee Service, Company Service, Payroll Service webhook events

flowchart LR
subgraph FE[Frontend (React + Vite)]
UI[Admin/Employee UI]
end

subgraph BE[Backend]
API[FastAPI]
Worker[Worker: accrual scheduler\n+ payroll event processor]
end

subgraph DB[(PostgreSQL)]
P[(policies)]
A[(assignments)]
R[(requests)]
L[(ledger_entries)]
B[(balance_snapshots)]
H[(holidays)]
Audit[(audit_log)]
end

subgraph EXT[External services (future / mocked)]
ES[Employee Service]
CS[Company Service]
PS[Payroll Service\non_payroll_processed]
end

UI --> API
API --> DB
Worker --> DB
API --> ES
API --> CS
PS --> API

---

3. Domain modeling decisions

3.1 Use minutes as the canonical unit

- Store all balances and accrual amounts as integer minutes
- Avoid float drift and rounding surprises
- Convert "days" ↔ minutes via employee workday minutes

  3.2 Ledger-first, snapshot-accelerated balances

Source of truth: append-only ledger_entries.

Why:

- Auditability
- Policy version changes don’t rewrite history
- Easy to explain "how did we get this balance?"

Performance:

- Maintain balance_snapshots as a derived cache updated transactionally whenever we write ledger entries.

  3.3 Versioned policies

Policy updates create a new version row, never mutating prior versions.

- Allows "what policy was in effect on date X?"
- Makes audits and retroactive scenarios tractable

---

4. Database schema (SQLModel + Alembic)

4.1 Core tables

time_off_policy (logical grouping)

- id (pk)
- company_id
- key (stable identifier e.g. vacation-ft)
- category (VACATION/SICK/etc)
- created_at

time_off_policy_version

- id (pk)
- policy_id (fk)
- version (int)
- effective_from (date)
- effective_to (date, nullable)
- type (UNLIMITED / ACCRUAL)
- accrual_method (TIME / HOURS_WORKED / null)
- settings_json (jsonb) — validated by Pydantic discriminated unions
- created_by
- created_at
- change_reason

time_off_policy_assignment

- id
- company_id
- employee_id
- policy_id
- effective_from
- effective_to nullable
- created_by, created_at

time_off_request

- id
- company_id
- employee_id
- policy_id (category/policy requested against)
- start_at (timestamptz)
- end_at (timestamptz)
- requested_minutes (int)
- reason (text)
- status enum
- submitted_at, decided_at
- decided_by nullable
- decision_note nullable
- idempotency_key nullable unique per employee/company (optional, recommended)

time_off_ledger_entry

- id
- company_id
- employee_id
- policy_id
- policy_version_id (fk; "what rules did we apply when posting?")
- entry_type enum:
- ACCRUAL
- HOLD (pending)
- HOLD_RELEASE
- USAGE
- ADJUSTMENT
- EXPIRATION
- CARRYOVER
- amount_minutes (signed int)
- effective_at (timestamptz) — when it impacts balance
- source_type enum: REQUEST / PAYROLL / ADMIN / SYSTEM
- source_id (uuid/text)
- metadata_json (jsonb)
- unique constraint (source_type, source_id, entry_type) for idempotency

time_off_balance_snapshot

- company_id, employee_id, policy_id (composite pk)
- accrued_minutes
- used_minutes
- held_minutes
- available_minutes (derived but stored for speed)
- updated_at
- version (optimistic locking counter)

company_holiday

- id
- company_id
- date (date)
- name

audit_log

- id
- company_id
- actor_id
- entity_type (POLICY_VERSION / REQUEST / ASSIGNMENT / HOLIDAY / ADJUSTMENT)
- entity_id
- action (CREATE/UPDATE/DELETE/APPROVE/DENY/etc)
- before_json, after_json
- created_at

  4.2 Mermaid ER diagram

erDiagram
time_off_policy ||--o{ time_off_policy_version : has
time_off_policy ||--o{ time_off_policy_assignment : assigned_to
time_off_policy ||--o{ time_off_request : requested_against
time_off_policy ||--o{ time_off_ledger_entry : affects

time_off_policy_version ||--o{ time_off_ledger_entry : applied_as

time_off_request ||--o{ time_off_ledger_entry : generates

time_off_balance_snapshot }o--|| time_off_policy : per_policy

---

5. Policy settings schema (Pydantic)

Use a discriminated union for settings_json so validation is strict and migrations are manageable.

5.1 Common fields

- unit: "minutes" | "hours" | "days" (stored as minutes internally)
- allow_negative: bool
- negative_limit_minutes: int | null
- bank_cap_minutes: int | null
- tenure_tiers: list of {min_months, accrual_rate}

  5.2 Time-based accrual settings

- accrual_frequency: DAILY | MONTHLY | YEARLY
- accrual_timing: START_OF_PERIOD | END_OF_PERIOD
- rate_minutes_per_year OR rate_minutes_per_month OR rate_minutes_per_day
- proration: method for partial periods (default: prorate by days active)
- carryover: {enabled, cap_minutes, expires_after_days?}
- expiration: {enabled, expires_on_month_day? or expires_after_days}

  5.3 Hours-worked accrual settings

- accrual_ratio: {accrue_minutes: int, worked_minutes: int}
- Example: "1 hour per 24 hours worked" => {60, 1440}
- cap_minutes: optional "cap per year" or "cap per period"
- carryover and expiration also apply

---

6. Balance computation

6.1 Definitions

For a given (employee, policy):

- accrued = sum(entry.amount where entry_type in {ACCRUAL, ADJUSTMENT, CARRYOVER} and amount>0 ...)
- used = sum(abs(amount)) for USAGE` debits
- held = sum(abs(amount)) for HOLD` debits not yet released
- available = (accrued - used) - held unless unlimited

Unlimited policy:

- available = null (or a sentinel) and UI shows "Unlimited"
- Still track used (days taken)

  6.2 Invariants

- If allow_negative=false, then available >= 0 must hold after a SUBMIT (hold) or APPROVE (usage).
- If allow_negative=true, then available >= -negative_limit_minutes (if limit set).

  6.3 Concurrency control

When submitting/approving:

- In a single DB transaction:
  1.  SELECT ... FOR UPDATE the balance_snapshot row
  2.  Recompute/check invariant
  3.  Insert ledger entry(ies)
  4.  Update snapshot atomically

This prevents double-spend under concurrent requests.

---

7. Request duration calculation

Inputs:

- start_at, end_at (timezone-aware in API, stored as UTC)
- employee work schedule:
- default: Mon–Fri 9–5
- optional override: 6-hour day, custom start/end

Algorithm (high-level): 1. Convert to employee timezone. 2. Iterate each day in range:

- If weekend → 0
- If holiday → 0
- Otherwise count overlap minutes between [start_at,end_at] and [workday_start,workday_end] 3. Sum minutes.

Edge cases:

- Partial days
- DST boundaries (use timezone-aware arithmetic)
- Requests outside working hours (clip to schedule)

---

8. Workflow details

8.1 Submit request (creates hold)

sequenceDiagram
participant U as Employee UI
participant API as FastAPI
participant DB as Postgres

U->>API: POST /requests (start,end,policy,reason)
API->>DB: BEGIN
API->>DB: Lock balance_snapshot FOR UPDATE
API->>DB: Validate policy assignment + overlaps + invariant
API->>DB: Insert request (SUBMITTED)
API->>DB: Insert ledger_entry HOLD (-minutes)
API->>DB: Update balance_snapshot (held += minutes; available -= minutes)
API->>DB: COMMIT
API-->>U: 201 Created + updated balance

8.2 Approve request

- Insert HOLD_RELEASE (+minutes)
- Insert USAGE (-minutes)
- Update snapshot: held decreases, used increases (available unchanged vs post-hold)

  8.3 Deny/cancel request

- Insert HOLD_RELEASE (+minutes)
- Update snapshot: held decreases, available increases

---

9. API surface (FastAPI)

9.1 Conventions

- REST-ish resources
- Company-scoped routes: /companies/{company_id}/...
- Auth (dev):
- simplest: header X-Company-Id + X-User-Id + X-Role
- production: JWT + RBAC middleware
- Pagination: cursor or offset for lists

  9.2 Endpoints

Policies

- GET /companies/{company_id}/policies
- POST /companies/{company_id}/policies
- GET /companies/{company_id}/policies/{policy_id}
- PUT /companies/{company_id}/policies/{policy_id} (creates new policy version)
- GET /companies/{company_id}/policies/{policy_id}/versions

Assignments

- POST /companies/{company_id}/policies/{policy_id}/assignments
- GET /companies/{company_id}/policies/{policy_id}/assignments
- DELETE /companies/{company_id}/assignments/{assignment_id} (end-date assignment)

Balances

- GET /companies/{company_id}/employees/{employee_id}/balances
- GET /companies/{company_id}/employees/{employee_id}/ledger?policy_id=...

Requests

- POST /companies/{company_id}/requests
- GET /companies/{company_id}/requests?status=pending&policy_id=...
- GET /companies/{company_id}/requests/{request_id}
- POST /companies/{company_id}/requests/{request_id}/approve
- POST /companies/{company_id}/requests/{request_id}/deny
- POST /companies/{company_id}/requests/{request_id}/cancel

Holidays

- GET /companies/{company_id}/holidays
- POST /companies/{company_id}/holidays
- DELETE /companies/{company_id}/holidays/{holiday_id}

Payroll webhook (dev + future)

- POST /webhooks/payroll_processed
- payload includes payroll_run_id, period dates, employee hours worked
- idempotent: ignore if already processed

---

10. Accrual engine

10.1 Time-based accrual (scheduled)

Worker runs daily (or monthly) and:

- finds active assignments
- selects policy version effective today
- computes accrual increment and posts ACCRUAL entry
- enforces bank cap
- handles year-end carryover/expiration by posting CARRYOVER/EXPIRATION

  10.2 Hours-worked accrual (event-driven)

On payroll webhook:

- for each employee:
- get hours worked → minutes worked
- for each hours-worked policy assignment:
- accrual = worked_minutes \* (accrue_minutes / worked_minutes_ratio)
- post ACCRUAL with source_type=PAYROLL and source_id=(payroll_run_id, employee_id, policy_id)

  10.3 Mid-period join / proration

If employee starts mid-period:

- If accrual is daily: naturally prorated
- If accrual is monthly-at-start: on assignment create a one-time prorated accrual "catch-up" entry for the remaining portion (policy-configurable)

---

11. Frontend design

11.1 Screens/pages

- Admin
- Policies list (cards like assignment screenshot)
- Policy detail (versions + settings + assignments)
- Requests inbox (pending approvals)
- Employee lookup (balances + ledger)
- Holidays admin
- Employee
- My balances
- My requests list
- Request time off modal (reason, category, dates, hours/minutes)

  11.2 UI kit

- Tailwind + shadcn/ui approach:
- Dialog, dropdown/select, date picker, tables
- matches Warp’s approach of composing strong primitives ￼

---

12. Repo structure

Recommended monorepo:

/
backend/
app/
alembic/
tests/
pyproject.toml
Dockerfile
frontend/
src/
index.html
package.json
vite.config.ts
Dockerfile
docs/
prd.md
tdd.md
architecture.md
api.md
decisions/
adr-0001-ledger-vs-derived.md
docker-compose.yml
Makefile
.github/workflows/ci.yml
README.md

---

13. Docker & Make targets

docker-compose services

- db (postgres)
- api (fastapi + uvicorn –reload)
- worker (python process for accrual + backfills)
- frontend (vite dev server)

Makefile targets (minimum)

- make dev → start all services
- make down → stop all
- make logs → tail logs
- make api-shell → exec into api
- make migrate → run alembic upgrade head
- make test → backend tests
- make lint → ruff/format/typecheck
- make fe → run frontend dev server (if not in compose)

---

14. Testing strategy (backend-first)

Tools

- pytest + pytest-asyncio
- httpx AsyncClient against FastAPI app
- Postgres per test run (CI service container)
- Alembic migrations run in CI before tests

Required coverage

- Enforce coverage threshold (e.g. 90%+)
- Critical property-style tests:
- submitting/approving/denying/cancelling maintains invariants
- idempotency of payroll events and approval endpoints
- proration and holiday exclusions

CI pipeline (GitHub Actions)

- backend:
- install
- lint (ruff)
- typecheck (pyright or mypy)
- run migrations
- run tests + coverage
- frontend:
- typecheck + build (and optionally lint)

---

15. Future deployment target (documented, not required now)

Terraform-managed AWS (target)

- VPC + subnets
- RDS Postgres
- ECS/Fargate service for API + worker
- ALB + HTTPS
- Secrets Manager for DB creds/JWT
- CloudWatch logs/metrics

GitHub Actions deploy (target)

- on merge to main:
- build docker images
- push to ECR
- terraform plan/apply
- run migrations
- deploy new task definition
