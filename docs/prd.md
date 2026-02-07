Employee Time Off Tracking

1. Overview

Problem

Companies need flexible time-off policies (unlimited or accrual-based) that can vary by employee group (full-time vs part-time, employee vs contractor, etc.). Employees need to see balances, request time off for specific dates/times, and get approvals from admins. The system must support accrual by time (e.g., 20 days/year) and by hours worked (e.g., proportional to hours from payroll events), and remain auditable and robust under policy changes and edge cases. ￼

Product vision

Build a fast, reliable, audit-first Time Off system with:

- Flexible policy modeling (versioned policies, arbitrary employee assignments)
- Accurate balance computation with strong invariants
- Clean approvals workflow
- First-class audit log (who/what/when/why)
- A Warp-inspired UI: minimal, crisp, high-signal, detail-obsessed, "ship it but ship it right" mindset ￼

---

2. Personas & roles

Employee

- Views balances and history
- Requests time off (category + dates/times + reason)
- Cancels pending requests

Admin (Company admin / HR / Payroll ops)

- Creates and updates policies
- Assigns employees to policies
- Approves/denies requests
- Adds manual adjustments (corrections, special grants)
- Manages holiday calendar
- Runs reports and audits changes

System integrations (future-real, mocked locally)

- Employee Service: employee metadata, pay type, schedule (e.g., 6-hour day), timezone
- Company Service: company identity, settings
- Payroll Service: emits on_payroll_processed event with employee hours worked ￼on-goals

Goals (v1 "complete") 1. Policy CRUD:

- Unlimited or accrual-based
- Accrual based on (a) time, (b) hours worked
- Tenure tiers, carryover & expiration, negative balance config 2. Assign employees to policies with effective dates 3. Track balances and "taken" amounts per policy/category 4. Request time off:
- Dates/times
- Validation against schedule, holidays, overlaps
- Creates pending hold that impacts "available" 5. Approval workflow:
- Approve/deny; balance updates correctly and idempotently 6. Auditability:
- Versioned policies
- Immutable ledger events for balance changes
- Audit log of every mutation 7. DX:
- Fully dockerized
- make commands run everything
- Fast refresh (Vite HMR + Uvicorn reload) 8. QA:
- Strong backend test coverage enforced in CI
- FE testing optional/minimal

Non-goals (initially)

- Full org chart / manager chain approvals (v2)
- Country-specific statutory leave law computation (future)
- Full calendar sync (Google/Outlook) (future)
- Payroll calculation itself (we only consume payroll summaries)

---

4. Key UX principles

Guidance:

- Use Warp's product/design mindset: "obsess over every flow, every edge case," "relentless pursuit of details," and "quality vs speed" without trading either away. ￼
- Implementation approach: use a strong component primitive system with good ergonomics. Warp has publicly discussed using shadcn-style component composition in their UI work. ￼
- The Warp design page references userinterface.wiki as a resource; treat it as optional inspiration for interaction patterns and micro-UX. ￼

---

5. User stories

Policies & assignments

- As an admin, I can create a "Vacation" policy that accrues 20 days/year, monthly, capped at 30 days.
- As an admin, I can create a "Sick" policy that accrues per payroll hours worked.
- As an admin, I can assign employees to a policy (effective from a date).
- As an admin, I can update a policy without destroying audit history.

Balances

- As an employee, I can see:
- Available balance
- Pending (held) balance
- Taken (approved usage)
- Accrued-to-date
- As an admin, I can view balances for any employee.

Time off requests

- As an employee, I can request time off for dates/times and see how it affects availability.
- As an employee, I can cancel a pending request.

Approvals

- As an admin, I can approve/deny a request with an optional comment.
- System updates balances and retains full audit trail.

Bonus/advanced

- Custom work hours per employee (6-hour day)
- Company holiday calendar that excludes holidays from deductions
- Carryover caps and expiration at year-end
- Tenure-based accrual tiers

---

6. Functional requirements

6.1 Policy model

Policy must support:

- unlimited vs accrual_based
- accrual method:
- time_based (daily/monthly/yearly schedule)
- hours_worked_based (from payroll events)
- units: store internally as minutes (integer)
- optional:
- negative balance allowed + limit
- max cap ("bank cap")
- carryover + cap
- expiration behavior
- tenure tiers

  6.2 Assignments

- Many employees can be assigned to the same policy
- One employee can have multiple policies (different categories)
- Assignments have effective start (and optional end)
- Assignments are auditable and version-aware

  6.3 Request calculation rules

Assumptions:

- Standard work schedule: Mon–Fri, 9am–5pm (8 hours) unless employee-specific override
  Rules:
- Requested duration computed in minutes using employee schedule
- Exclud ￼holidays (company calendar)
- Disallow overlap with approved requests in the same category (configurable)

  6.4 Approvals and balance updates

- Requests have state machine:
- DRAFT → SUBMITTED → APPROVED|DENIED (and CANCELLED)
- On submit: create "hold" against available
- On approval: convert hold → usage
- On denial/cancel: release hold
- Must be idempotent and safe under retries

  6.5 Policy updates

- Policy updates create a new version effective from a date
- Past ledger events remain unchanged
- Retroactive policy changes require explicit "adjustment" entries (admin action or backfill job)

  6.6 Payroll event consumption

- Consume on_payroll_processed with employee hours worked for that pay period
- For hour-worked policies, post accrual ledger entries derived from those hours ￼oll run ID

  6.7 Audit

- Record:
- who did what
- before/after snapshot (for mutable records)
- timestamp
- reason/comment when applicable
- Ledger entries immutable and append-only

---

7. Success metrics

- Correctness:
- All invariants covered by tests
- No negative balances unless allowed by policy
- Idempotent processing of payroll events and approvals
- DX:
- New dev can run make dev and be productive in <5 minutes
- CI reliably runs tests, lint, type checks
- Product:
- Admin can create policy + assign employees + see balances + approve request end-to-end

---

8. Risks & mitigations

- Policy complexity creep → Mitigate with typed policy schemas and versioning; avoid untyped "magic JSON".
- Time calculations (DST, timezone) → Store in UTC, convert using employee timezone for UI and working-hours computation.
- Concurrency (two requests submitted at once) → Transactional holds with row locking + invariants + idempotency keys.
- Retroactive changes → Require explicit adjustment entries for auditability.

---

9. Out of scope but documented "future target"

- Terraform-managed AWS (RDS, ECS/Fargate, ALB, CloudWatch, Secrets Manager)
- GitHub Actions deploy pipeline (build → push → migrate → deploy)
- Event ingestion via queue (SNS/SQS) instead of webhook
