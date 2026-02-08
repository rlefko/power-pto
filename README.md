# Power PTO

[![CI](https://github.com/rlefko/power-pto/actions/workflows/ci.yml/badge.svg)](https://github.com/rlefko/power-pto/actions/workflows/ci.yml)
[![CodeQL](https://github.com/rlefko/power-pto/actions/workflows/codeql.yml/badge.svg)](https://github.com/rlefko/power-pto/actions/workflows/codeql.yml)

A full-stack employee time-off tracking system built for the [Warp](https://joinwarp.com/) product engineer take-home assessment. Power PTO supports flexible policies (unlimited and accrual-based), ledger-first balance tracking, approval workflows, and full audit trails, all backed by a React frontend and a FastAPI + PostgreSQL backend.

---

## Assessment Requirements & How They're Met

The assessment asks for a robust system capable of tracking employee time off, including policies, requests, balances, accrual mechanisms, approval workflows, and balance updates. Below is a mapping of every requirement to its implementation in Power PTO.

### Core Requirements

| Requirement | Implementation |
|---|---|
| Policy storage (unlimited + accrual) | Versioned policies with Pydantic discriminated-union settings supporting three types: unlimited, time-based accrual, and hours-worked accrual. Six categories (Vacation, Sick, Personal, Bereavement, Parental, Other). |
| Balance tracking | Ledger-first architecture: an append-only `time_off_ledger_entry` table is the source of truth, with `time_off_balance_snapshot` as a transactionally-updated derived cache for O(1) reads. Formula: `available = accrued - used - held`. |
| Time-based accrual | Background worker runs a daily cycle, computing accruals for all active TIME assignments. Supports daily, monthly, and yearly frequencies with configurable timing (start or end of period). |
| Hours-worked accrual | `POST /webhooks/payroll_processed` endpoint consumes payroll events and posts ACCRUAL ledger entries proportional to hours worked. Idempotent by `payroll_run_id`. |
| Employee time-off requests | Full state machine: DRAFT to SUBMITTED to APPROVED, DENIED, or CANCELLED. Submit creates a HOLD entry reserving minutes; approve converts to USAGE; deny/cancel releases the HOLD. |
| Admin approvals | Approve/deny endpoints with optional decision notes. Balance updated atomically within the same transaction. |
| Flexible employee grouping | Any employee can be assigned to any combination of policies via `time_off_policy_assignment` with effective date ranges. Supports Full-Time vs Part-Time, Employee vs Contractor, or any arbitrary grouping. |

### Considerations Addressed

The assessment raises three specific questions. Here's how Power PTO handles each:

| Question | Answer |
|---|---|
| **What if a company wants to update accrual settings?** | Policy updates create a new `time_off_policy_version` row. Prior versions are never mutated, preserving full audit history. The system can answer "what policy was in effect on date X?" for any point in time. Past ledger events remain unchanged; retroactive changes require explicit adjustment entries. |
| **Should the system allow negative balances?** | Configurable per-policy. `allow_negative` (boolean) with an optional `negative_limit_minutes` cap. When `allow_negative=false`, the balance invariant (`available >= 0`) is enforced at submit and approval time inside a locked transaction. |
| **What about mid-period joins?** | `DAYS_ACTIVE` proration calculates proportional accrual based on the number of days the employee was active during the period. For example, joining halfway through a month on a monthly accrual policy yields 50% of the monthly rate. Proration is policy-configurable (can be set to `NONE` to grant the full amount). |

### Bonus Challenges (All Implemented)

| Challenge | Implementation |
|---|---|
| **Custom work hours** | Each employee has a `workday_minutes` field (default 480 = 8 hours). Supports 6-hour days (360 min), or any custom schedule. The duration calculator uses this value when computing requested minutes, and the accrual engine respects it for rate calculations. |
| **Company holiday calendars** | `company_holiday` table stores company-specific holidays. The duration calculator automatically excludes holidays when computing requested minutes for time-off requests. Holidays are managed via CRUD endpoints with year-based filtering. |
| **Carryover & expiration** | Year-end carryover processing (runs Jan 1) with configurable caps (`cap_minutes`). Two expiration modes: calendar-date expiration (`expires_on_month`/`expires_on_day`) and post-carryover expiration (`expires_after_days`). Both post EXPIRATION ledger entries. |
| **Tenure-based policies** | `tenure_tiers` in policy settings define accrual rate overrides by months of service. Example: 0-60 months = 20 days/year, 60+ months = 24 days/year. The accrual engine resolves the employee's hire date against the tier table to determine the correct rate. |

### Evaluation Criteria

| Criterion | How It's Demonstrated |
|---|---|
| **Core flows and requirements met** | All core requirements plus all four bonus challenges are fully implemented with working API endpoints, business logic, and UI. |
| **Well thought out** | Edge cases handled throughout: concurrent request submission (row-level locking), idempotent payroll processing, mid-period proration, holiday-aware duration calculation, overlap detection, negative balance enforcement. See [Design Decisions](#design-decisions--tradeoffs) below. |
| **Auditable** | Every mutation writes to `audit_log` with actor, entity, action, and before/after JSON snapshots. The ledger is append-only and immutable. Policy updates create new versions rather than mutating history. |
| **Clear communication** | This README, plus six detailed reference documents: [PRD](docs/prd.md), [TDD](docs/tdd.md), [Architecture](docs/architecture.md), [API Reference](docs/api.md), [Data Model](docs/data-model.md), [Deployment Plan](docs/deployment.md). |

---

## Feature Highlights

### Policy Management
- Create, read, update policies with three types: **Unlimited**, **Time-Based Accrual**, and **Hours-Worked Accrual**
- Six categories: Vacation, Sick, Personal, Bereavement, Parental, Other
- Immutable policy versioning: every update creates a new version, preserving full history
- Discriminated-union settings validated by Pydantic (no untyped "magic JSON")
- Configurable bank caps, negative balance limits, and display units (minutes, hours, days)

### Assignment Management
- Assign any employee to any combination of policies with effective date ranges
- Half-open interval semantics: `[effective_from, effective_to)`
- Overlap detection prevents conflicting assignments to the same policy
- Soft delete via end-dating (sets `effective_to`, preserving history)

### Request Workflow
- Full state machine: DRAFT to SUBMITTED to APPROVED / DENIED / CANCELLED
- Submit creates a HOLD ledger entry that reserves the requested minutes from the available balance
- Approve converts the HOLD to USAGE (HOLD_RELEASE + USAGE entries)
- Deny or cancel releases the HOLD, restoring availability
- Duration calculator excludes weekends and company holidays automatically
- Client-provided idempotency keys prevent duplicate submissions

### Balance System
- **Ledger-first architecture**: the append-only `time_off_ledger_entry` table is the single source of truth
- **Snapshot acceleration**: `time_off_balance_snapshot` is a derived cache updated transactionally alongside every ledger write for O(1) balance reads
- **Concurrency control**: `SELECT ... FOR UPDATE` on the snapshot row prevents double-spend under concurrent requests
- **Optimistic locking**: snapshot `version` column incremented on every update
- **Balance formula**: `available = accrued - used - held`
- **Fallback**: if no snapshot exists, balance is recomputed from the full ledger

### Accrual Engine
- **Time-based**: background worker processes all active TIME assignments daily, supporting daily, monthly, and yearly frequencies
- **Hours-worked**: payroll webhook endpoint computes accrual proportional to worked minutes using a configurable ratio (e.g., 1 hour accrued per 24 hours worked)
- **Proration**: `DAYS_ACTIVE` method handles mid-period joins automatically
- **Tenure tiers**: accrual rates that scale with employee tenure (e.g., higher rate after 5 years)
- **Bank caps**: maximum accrued balance enforced at accrual time
- **Idempotency**: unique constraint on `(source_type, source_id, entry_type)` prevents duplicate ledger entries

### Year-End Processing
- **Carryover**: runs on Jan 1, carries unused balance forward with optional caps
- **Expiration**: two modes - calendar-date (e.g., expires March 31) and post-carryover (e.g., expires 90 days after carryover)
- Both post dedicated ledger entries (CARRYOVER, EXPIRATION) for full auditability

### Holiday Calendar
- Company-specific holidays with CRUD management
- Year-based filtering for easy calendar views
- Duration calculator automatically excludes holidays from time-off deductions
- Unique constraint prevents duplicate holidays on the same date

### Audit Trail
- Every mutation writes to `audit_log` with actor ID, entity type, entity ID, action, and before/after JSON snapshots
- Ledger entries are immutable and append-only (corrections are new entries with opposite signs)
- Policy changes create new versions, never mutating prior history
- Filterable by entity type, action, actor, and date range

### Admin Tools
- Manual balance adjustments with required reason (posts ADJUSTMENT ledger entry)
- Trigger accruals, carryover, and expiration processing on-demand via admin endpoints
- Balance summary reports across all employees
- Ledger export with policy, employee, and date range filters

### Frontend
- **10 pages** across employee and admin roles, built with React 19, TypeScript, and shadcn/ui (Radix + Tailwind)
- **Employee views**: My Balances (balance cards with accrued/used/held/available), My Requests (filterable table with cancel action)
- **Admin views**: Policy management (create/edit with conditional form fields per policy type), Approval queue (approve/deny with notes), Employee management (detail pages with balance, ledger, and assignment tabs), Holiday calendar (year-based CRUD), Audit log (filterable by entity and action)
- TanStack Query for server state with automatic cache invalidation on mutations
- React Hook Form + Zod for form validation
- Dev-mode user/role switcher in the header for testing different personas
- Loading skeletons, error boundaries, toast notifications, and empty states throughout

### Developer Experience
- **One-command setup**: `make setup` installs prerequisites, builds Docker images, runs migrations, and seeds demo data
- **Hot reload**: Uvicorn `--reload` for the backend, Vite HMR for the frontend
- **Seed data**: 4 employees, 4 policies, 6 holidays, assignments, balance grants, and a pending request
- **Interactive API docs**: Swagger UI at `/docs` and ReDoc at `/redoc`
- **Pre-commit hooks**: ruff + ty (backend), ESLint + Prettier (frontend) run automatically before every commit
- **CI pipeline**: 5 parallel GitHub Actions jobs (backend lint, typecheck, test; frontend lint, build)
- **90%+ backend test coverage** enforced in CI

---

## Architecture Overview

Power PTO follows a monorepo structure with four Docker services:

```
Frontend (React + Vite)  -->  API (FastAPI + Uvicorn)  -->  PostgreSQL
                              Worker (Accrual Scheduler) --^
```

- **Frontend**: Single-page React app with feature-based module structure. Communicates via Axios client that proxies `/api/*` to the backend. TanStack Query manages server state.
- **API Server**: FastAPI application handling all REST endpoints, business rules, and database transactions. Company-scoped routes with dev auth via `X-Company-Id`, `X-User-Id`, `X-Role` headers.
- **Worker**: Standalone Python process running a 24-hour accrual cycle (time-based accruals, carryover, expiration).
- **Database**: PostgreSQL 17 with 8 core tables + audit log, managed by Alembic migrations.

The core data model uses a **ledger-first, snapshot-accelerated** approach where the append-only ledger is the source of truth and balance snapshots are transactionally-updated derived caches. See [Architecture](docs/architecture.md) and [Data Model](docs/data-model.md) for full details including ER diagrams, sequence diagrams, and concurrency control flows.

---

## Tech Stack

**Backend:** Python 3.13+, FastAPI, PostgreSQL 17, SQLModel, Alembic, Pydantic

**Frontend:** TypeScript, React 19, Vite, shadcn/ui (Radix + Tailwind), TanStack Query

**Infra:** Docker, Docker Compose, Make, GitHub Actions CI, pre-commit hooks

**Code Quality:** ruff, ty, ESLint, Prettier

---

## Project Structure

```
backend/     - FastAPI application, Alembic migrations, and tests
frontend/    - React/Vite single-page application
docs/        - Product requirements, technical design, and architecture
```

---

## Getting Started

### One-Command Setup

The setup script installs all prerequisites (Docker, Node.js, yarn, GitHub CLI, pre-commit), builds the Docker images, runs migrations, and seeds demo data:

```bash
make setup
```

Once complete, the app is running at the URLs below. No other steps needed.

### Manual Setup

If you already have Docker, Docker Compose, Make, and Node.js/yarn installed:

```bash
# Clone and enter the repo
git clone https://github.com/rlefko/power-pto.git
cd power-pto

# Install pre-commit hooks
pre-commit install

# Install frontend dependencies (needed for linting)
cd frontend && yarn install && cd ..

# Build and start all services (db, api, frontend)
make up

# In another terminal, run migrations and seed demo data
make migrate
make seed
```

### Service URLs

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |
| API Docs (ReDoc) | http://localhost:8000/redoc |

To also start the background accrual worker:

```bash
docker compose --profile worker up
```

---

## Seed Data

`make seed` populates the database with demo data for development:

- **4 employees:** Alice Johnson, Bob Smith, Carol Williams, Dave Brown
- **4 policies:** standard-pto (accrual), unlimited-vacation, sick-leave (accrual), hourly-pto (hours-worked)
- **6 holidays** for 2026
- **Policy assignments** linking employees to policies
- **Balance adjustments** (10-day accrual grants)
- **A pending time-off request** from Bob Smith (2 days of standard PTO)

The seed script is idempotent and can be re-run after `make clean` to reset data.

---

## Make Commands

| Command | Description |
|---------|-------------|
| `make setup` | One-command dev environment setup (installs prerequisites, builds, migrates, seeds) |
| `make up` | Start all services in foreground |
| `make up-d` | Start all services detached |
| `make down` | Stop all services |
| `make build` | Build Docker images |
| `make clean` | Stop services, remove volumes and local images |
| `make migrate` | Run Alembic database migrations |
| `make seed` | Seed the database with demo data |
| `make test` | Run backend tests |
| `make test-cov` | Run backend tests with coverage report |
| `make lint` | Run all linters (ruff, ty, ESLint, Prettier) |
| `make logs` | Tail service logs |
| `make api-shell` | Open a shell in the API container |
| `make fe` | Run frontend dev server standalone (outside Docker) |

### Running a Single Test

```bash
docker compose exec api uv run pytest tests/path/to/test_file.py::test_function_name -v
```

---

## Design Decisions & Tradeoffs

These are the key architectural choices and the reasoning behind them:

**Ledger-first over direct balance mutation.** Directly updating a single balance row is simpler, but it makes it impossible to answer "how did we get this number?" The append-only ledger gives full auditability, makes debugging straightforward, and means policy version changes never rewrite history. The snapshot cache eliminates the read-performance concern.

**Immutable policy versioning over mutable policies.** Mutating a policy row in-place loses the record of what was in effect when a given accrual or request happened. Creating new version rows means every ledger entry can reference the exact policy version that was applied, enabling accurate audits and clean retroactive reasoning.

**Integer minutes over floats or decimals.** Floating-point arithmetic introduces drift and rounding surprises that are unacceptable in a financial-adjacent system. Integer minutes are exact, and conversion to display units (hours, days) happens only at the presentation layer using the employee's `workday_minutes`.

**`SELECT ... FOR UPDATE` for concurrency control.** When two requests for the same employee are submitted simultaneously, both could pass the balance check before either writes. Row-level locking on the balance snapshot within a single transaction prevents this double-spend. Combined with the optimistic locking `version` column, this provides defense in depth.

**VARCHAR over native PostgreSQL enums.** Native PG enums require `ALTER TYPE ... ADD VALUE` for new values, which can't run inside a transaction and creates migration headaches. VARCHAR columns with application-layer validation (Python enums) are simpler to evolve and test.

**Append-only ledger with correction entries.** Ledger entries are never updated or deleted. If a correction is needed, a new entry with the opposite sign is posted. This preserves the full history and makes the system trivially auditable.

---

## How This Was Built

### Standing on the shoulders of prior work

The infrastructure layer of this project (Docker Compose configuration, Makefile targets, CI pipeline structure, pre-commit hook setup, and the general project scaffolding) follows patterns established in prior personal and professional projects and adapted from open-source best practices. This is intentional: re-using proven infrastructure patterns means more time spent on the actual domain problem rather than reinventing DevOps scaffolding from scratch. The same principle applies to the frontend component system, where shadcn/ui provides a set of accessible, composable primitives that align with Warp's publicly discussed UI approach of composing strong component primitives with Radix and Tailwind.

Learning from past projects and the open-source ecosystem, then applying those lessons to new problems, is a core part of how I work. The infrastructure is the platform; the domain model, business logic, and system design are the product.

### Claude Code as a development tool

Claude Code was used as a development accelerator throughout this project. Specifically, it helped with:

- **Scaffolding and boilerplate**: Docker configurations, CI workflow setup, component templates, test fixture generation, and repetitive CRUD endpoint wiring
- **Velocity on implementation**: translating the designed schemas into SQLModel definitions, building out form components, wiring TanStack Query hooks, and iterating on frontend layouts
- **Documentation**: drafting and refining the detailed reference documents (API reference, data model docs, architecture write-ups)

The core architectural decisions were mine: choosing a ledger-first balance model, designing the policy versioning system, working through the concurrency control approach, defining the request state machine and hold/release mechanics, and reasoning through the accrual engine's proration and tenure tier logic. Claude Code was a force multiplier for velocity, not a substitute for the design thinking that drives a system like this.

I think this is worth highlighting because it reflects how modern software engineering actually works. The best engineers aren't the ones who refuse to use tools; they're the ones who use every tool available while maintaining a deep understanding of the systems they build. The design decisions documented in this README and the [TDD](docs/tdd.md) represent careful thought about real-world tradeoffs. Claude Code helped me ship the implementation faster.

---

## Future Extensions

These are documented targets for evolving Power PTO beyond its current state:

- **JWT + RBAC authentication** to replace the dev-mode header-based auth scheme. The `AuthContext` interface is designed to make this a drop-in replacement.
- **Manager chain approvals** for multi-level approval workflows (e.g., direct manager then HR).
- **Calendar sync** with Google Calendar and Outlook for automatic out-of-office blocking.
- **Country-specific statutory leave rules** for companies operating across multiple jurisdictions.
- **Event-driven accruals** via a message queue (SNS/SQS) instead of the current webhook, for better decoupling and retry guarantees.
- **AWS deployment** on ECS Fargate with RDS, ALB, and CloudWatch. Fully documented in [docs/deployment.md](docs/deployment.md) with Terraform resource outlines and a CI/CD pipeline design.
- **Notification system** for email/Slack alerts on request status changes.
- **Bulk operations** for mass policy assignment and bulk accrual adjustments.

---

## Documentation

| Document | Description |
|----------|-------------|
| [Product Requirements](docs/prd.md) | Business goals, personas, user stories, functional requirements |
| [Technical Design](docs/tdd.md) | System design, domain modeling, schema, API surface, accrual engine |
| [Architecture](docs/architecture.md) | Component layout, data flows, concurrency control, CI/CD pipeline |
| [API Reference](docs/api.md) | Complete endpoint documentation with request/response examples |
| [Data Model](docs/data-model.md) | Database schema, ER diagram, table definitions, design decisions |
| [Deployment Plan](docs/deployment.md) | Future AWS architecture, Terraform outline, cost estimate |
