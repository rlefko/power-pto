# API Reference

Complete endpoint reference for the Power PTO REST API. All endpoints are served by the FastAPI backend on port 8000. Interactive documentation is available at `/docs` (Swagger UI) and `/redoc` (ReDoc) in non-production environments.

## Authentication

### Development Mode

Authentication uses HTTP headers on every request:

| Header | Type | Required | Description |
|--------|------|----------|-------------|
| `X-Company-Id` | UUID | Yes | Tenant/company identifier |
| `X-User-Id` | UUID | Yes | Current user identifier |
| `X-Role` | string | No | `"admin"` or `"employee"` (default: `"employee"`) |

All company-scoped endpoints validate that the `company_id` path parameter matches `X-Company-Id`.

### Role-Based Access

- **Any** — Both `admin` and `employee` roles can access
- **Admin** — Only `admin` role; returns `403 Forbidden` for employees

## Common Patterns

### Pagination

List endpoints support offset-based pagination:

| Parameter | Type | Default | Range |
|-----------|------|---------|-------|
| `offset` | int | 0 | >= 0 |
| `limit` | int | 50 | 1–100 |

Paginated responses include:

```json
{
  "items": [...],
  "total": 142
}
```

### Error Responses

All errors return a JSON body:

```json
{
  "error": "Human-readable error message",
  "detail": "Additional context (optional)",
  "status_code": 400
}
```

Common status codes: `400` (validation), `403` (forbidden), `404` (not found), `409` (conflict), `422` (unprocessable entity).

### Company-Scoped Routes

All resource endpoints are scoped under `/companies/{company_id}/...`. The `company_id` path parameter is validated against the `X-Company-Id` header.

---

## Health

### `GET /health`

Returns the health status of the API and database connectivity.

**Auth:** None required

**Response:**

```json
{
  "status": "ok",
  "version": "0.1.0",
  "environment": "development"
}
```

| Field | Values |
|-------|--------|
| `status` | `"ok"`, `"degraded"`, `"error"` |

---

## Policies

### `POST /companies/{company_id}/policies`

Create a new time-off policy with its initial version.

**Auth:** Admin

**Request body:**

```json
{
  "key": "vacation-ft",
  "category": "VACATION",
  "version": {
    "effective_from": "2025-01-01",
    "settings": {
      "type": "ACCRUAL",
      "accrual_method": "TIME",
      "unit": "DAYS",
      "accrual_frequency": "MONTHLY",
      "accrual_timing": "START_OF_PERIOD",
      "rate_minutes_per_year": 9600,
      "proration": "DAYS_ACTIVE",
      "allow_negative": false,
      "bank_cap_minutes": 14400,
      "tenure_tiers": [],
      "carryover": { "enabled": false },
      "expiration": { "enabled": false }
    },
    "change_reason": "Initial policy creation"
  }
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `key` | string | Yes | 1–255 chars, unique per company |
| `category` | string | Yes | `VACATION`, `SICK`, `PERSONAL`, `BEREAVEMENT`, `PARENTAL`, `OTHER` |
| `version` | object | Yes | Initial version configuration |
| `version.effective_from` | date | Yes | When this version takes effect |
| `version.settings` | object | Yes | Discriminated union (see [Policy Settings](#policy-settings)) |
| `version.change_reason` | string | No | Explanation for the change |

**Response:** `201 Created` — [PolicyResponse](#policyresponse)

### `GET /companies/{company_id}/policies`

List all policies for the company.

**Auth:** Any

**Query params:** `offset`, `limit`

**Response:** `200 OK` — `{ items: PolicyResponse[], total: int }`

### `GET /companies/{company_id}/policies/{policy_id}`

Get a single policy with its current (latest) version.

**Auth:** Any

**Response:** `200 OK` — [PolicyResponse](#policyresponse)

### `PUT /companies/{company_id}/policies/{policy_id}`

Update a policy by creating a new version. The previous version's `effective_to` is set to the new version's `effective_from`.

**Auth:** Admin

**Request body:**

```json
{
  "version": {
    "effective_from": "2026-01-01",
    "settings": { ... },
    "change_reason": "Increased annual accrual rate"
  }
}
```

**Response:** `200 OK` — [PolicyResponse](#policyresponse)

### `GET /companies/{company_id}/policies/{policy_id}/versions`

List all versions of a policy, ordered by version number.

**Auth:** Any

**Query params:** `offset`, `limit`

**Response:** `200 OK` — `{ items: PolicyVersionResponse[], total: int }`

---

## Assignments

### `POST /companies/{company_id}/policies/{policy_id}/assignments`

Assign an employee to a policy.

**Auth:** Admin

**Request body:**

```json
{
  "employee_id": "550e8400-e29b-41d4-a716-446655440000",
  "effective_from": "2025-01-01",
  "effective_to": null
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `employee_id` | UUID | Yes | Employee to assign |
| `effective_from` | date | Yes | Assignment start date |
| `effective_to` | date | No | Assignment end date (null = ongoing) |

**Response:** `201 Created` — [AssignmentResponse](#assignmentresponse)

### `GET /companies/{company_id}/policies/{policy_id}/assignments`

List all assignments for a specific policy.

**Auth:** Any

**Query params:** `offset`, `limit`

**Response:** `200 OK` — `{ items: AssignmentResponse[], total: int }`

### `GET /companies/{company_id}/employees/{employee_id}/assignments`

List all policy assignments for a specific employee.

**Auth:** Any

**Query params:** `offset`, `limit`

**Response:** `200 OK` — `{ items: AssignmentResponse[], total: int }`

### `DELETE /companies/{company_id}/assignments/{assignment_id}`

End-date an assignment (soft delete). Sets `effective_to` to the provided date.

**Auth:** Admin

**Query params:**

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `effective_to` | date | today | When the assignment ends |

**Response:** `200 OK` — [AssignmentResponse](#assignmentresponse)

---

## Requests

### `POST /companies/{company_id}/requests`

Submit a new time-off request. Calculates duration in working minutes (excluding weekends and holidays), creates the request in `SUBMITTED` status, and posts a `HOLD` ledger entry against the employee's balance.

**Auth:** Any

**Request body:**

```json
{
  "employee_id": "550e8400-e29b-41d4-a716-446655440000",
  "policy_id": "660e8400-e29b-41d4-a716-446655440000",
  "start_at": "2025-06-02T09:00:00Z",
  "end_at": "2025-06-06T17:00:00Z",
  "reason": "Family vacation",
  "idempotency_key": "req-2025-06-vacation"
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `employee_id` | UUID | Yes | Requesting employee |
| `policy_id` | UUID | Yes | Policy to deduct from |
| `start_at` | datetime | Yes | Request start (UTC) |
| `end_at` | datetime | Yes | Request end (UTC); must be after `start_at` |
| `reason` | string | No | Optional reason |
| `idempotency_key` | string | No | Max 255 chars; prevents duplicate submissions |

**Response:** `201 Created` — [RequestResponse](#requestresponse)

**Errors:**
- `400` — No active assignment, insufficient balance, overlapping request
- `409` — Duplicate idempotency key

### `GET /companies/{company_id}/requests`

List time-off requests with optional filters.

**Auth:** Any

**Query params:**

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `status` | string | — | Filter by status: `DRAFT`, `SUBMITTED`, `APPROVED`, `DENIED`, `CANCELLED` |
| `policy_id` | UUID | — | Filter by policy |
| `employee_id` | UUID | — | Filter by employee |
| `offset` | int | 0 | Pagination offset |
| `limit` | int | 50 | Pagination limit (1–100) |

**Response:** `200 OK` — `{ items: RequestResponse[], total: int }`

### `GET /companies/{company_id}/requests/{request_id}`

Get a single time-off request.

**Auth:** Any

**Response:** `200 OK` — [RequestResponse](#requestresponse)

### `POST /companies/{company_id}/requests/{request_id}/approve`

Approve a submitted request. Posts `HOLD_RELEASE` and `USAGE` ledger entries.

**Auth:** Admin

**Request body (optional):**

```json
{
  "note": "Approved, enjoy your vacation!"
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `note` | string | No | Max 1000 chars |

**Response:** `200 OK` — [RequestResponse](#requestresponse)

### `POST /companies/{company_id}/requests/{request_id}/deny`

Deny a submitted request. Posts a `HOLD_RELEASE` ledger entry to restore the held balance.

**Auth:** Admin

**Request body (optional):**

```json
{
  "note": "Insufficient team coverage for that week"
}
```

**Response:** `200 OK` — [RequestResponse](#requestresponse)

### `POST /companies/{company_id}/requests/{request_id}/cancel`

Cancel a request. If the request was `SUBMITTED`, posts a `HOLD_RELEASE` ledger entry.

**Auth:** Any (the requesting employee or an admin)

**Response:** `200 OK` — [RequestResponse](#requestresponse)

---

## Balances & Ledger

### `GET /companies/{company_id}/employees/{employee_id}/balances`

Get all policy balances for an employee. Returns one entry per active policy assignment.

**Auth:** Any

**Response:** `200 OK`

```json
{
  "items": [
    {
      "policy_id": "660e8400-e29b-41d4-a716-446655440000",
      "policy_key": "vacation-ft",
      "policy_category": "VACATION",
      "accrued_minutes": 9600,
      "used_minutes": 2400,
      "held_minutes": 480,
      "available_minutes": 6720,
      "is_unlimited": false,
      "updated_at": "2025-06-01T12:00:00Z"
    }
  ],
  "total": 1
}
```

For unlimited policies, `available_minutes` is `null` and `is_unlimited` is `true`.

### `GET /companies/{company_id}/employees/{employee_id}/ledger`

Get paginated ledger entries for an employee and policy.

**Auth:** Any

**Query params:**

| Parameter | Type | Required | Notes |
|-----------|------|----------|-------|
| `policy_id` | UUID | Yes | Filter to a specific policy |
| `offset` | int | No | Default: 0 |
| `limit` | int | No | Default: 50 (1–100) |

**Response:** `200 OK` — `{ items: LedgerEntryResponse[], total: int }`

### `POST /companies/{company_id}/adjustments`

Create an admin balance adjustment. Posts an `ADJUSTMENT` ledger entry.

**Auth:** Admin

**Request body:**

```json
{
  "employee_id": "550e8400-e29b-41d4-a716-446655440000",
  "policy_id": "660e8400-e29b-41d4-a716-446655440000",
  "amount_minutes": 480,
  "reason": "Bonus day for on-call coverage"
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `employee_id` | UUID | Yes | Target employee |
| `policy_id` | UUID | Yes | Target policy |
| `amount_minutes` | int | Yes | Signed: positive to add, negative to deduct |
| `reason` | string | Yes | 1–1000 chars |

**Response:** `201 Created` — [LedgerEntryResponse](#ledgerentryresponse)

---

## Holidays

### `POST /companies/{company_id}/holidays`

Create a company holiday. Holidays are excluded from time-off duration calculations.

**Auth:** Admin

**Request body:**

```json
{
  "date": "2025-12-25",
  "name": "Christmas Day"
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `date` | date | Yes | Holiday date; unique per company |
| `name` | string | Yes | 1–255 chars |

**Response:** `201 Created` — [HolidayResponse](#holidayresponse)

### `GET /companies/{company_id}/holidays`

List company holidays with optional year filter.

**Auth:** Any

**Query params:**

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `year` | int | — | Filter by year |
| `offset` | int | 0 | Pagination offset |
| `limit` | int | 50 | Pagination limit (1–100) |

**Response:** `200 OK` — `{ items: HolidayResponse[], total: int }`

### `DELETE /companies/{company_id}/holidays/{holiday_id}`

Delete a company holiday.

**Auth:** Admin

**Response:** `204 No Content`

---

## Employees (Stub Service)

These endpoints manage employee records in an in-memory stub service. In production, employee data would come from an external Employee Service.

### `PUT /companies/{company_id}/employees/{employee_id}`

Create or update an employee.

**Auth:** Admin

**Request body:**

```json
{
  "first_name": "Jane",
  "last_name": "Doe",
  "email": "jane.doe@example.com",
  "pay_type": "SALARY",
  "workday_minutes": 480,
  "timezone": "America/New_York",
  "hire_date": "2024-03-15"
}
```

| Field | Type | Required | Default | Notes |
|-------|------|----------|---------|-------|
| `first_name` | string | Yes | — | 1–100 chars |
| `last_name` | string | Yes | — | 1–100 chars |
| `email` | string | Yes | — | 1–255 chars |
| `pay_type` | string | No | `"SALARY"` | `"SALARY"` or `"HOURLY"` |
| `workday_minutes` | int | No | 480 | 60–1440 |
| `timezone` | string | No | `"UTC"` | IANA timezone |
| `hire_date` | date | No | — | Used for tenure tier calculations |

**Response:** `200 OK` — [EmployeeResponse](#employeeresponse)

### `GET /companies/{company_id}/employees/{employee_id}`

Get a single employee.

**Auth:** Any

**Response:** `200 OK` — [EmployeeResponse](#employeeresponse)

### `GET /companies/{company_id}/employees`

List all employees for a company.

**Auth:** Any

**Response:** `200 OK` — `{ items: EmployeeResponse[], total: int }`

---

## Accruals

### `POST /companies/{company_id}/accruals/trigger`

Manually trigger time-based accruals for a specific date. Processes all active `TIME` accrual assignments for the company. Useful for testing and backfills.

**Auth:** Admin

**Query params:**

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `target_date` | date | today | Date to run accruals for |

**Response:** `200 OK`

```json
{
  "target_date": "2025-06-01",
  "processed": 12,
  "accrued": 10,
  "skipped": 2,
  "errors": 0
}
```

### `POST /companies/{company_id}/accruals/carryover`

Manually trigger year-end carryover processing. Only processes assignments with carryover-enabled policies when `target_date` is January 1.

**Auth:** Admin

**Query params:**

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `target_date` | date | today | Must be Jan 1 for carryover to fire |

**Response:** `200 OK`

```json
{
  "target_date": "2026-01-01",
  "carryovers_processed": 5,
  "expirations_processed": 2,
  "skipped": 3,
  "errors": 0
}
```

### `POST /companies/{company_id}/accruals/expiration`

Manually trigger balance expiration processing. Processes calendar-date expirations and post-carryover expirations.

**Auth:** Admin

**Query params:**

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `target_date` | date | today | Date to check expirations against |

**Response:** `200 OK` — Same shape as carryover response

---

## Payroll Webhook

### `POST /webhooks/payroll_processed`

Receive a payroll processed event and compute hours-worked accruals. This endpoint is called by an external Payroll Service. The `company_id` comes from the payload body, not the path or headers.

**Auth:** None (webhook endpoint)

**Request body:**

```json
{
  "payroll_run_id": "PR-2025-06-01",
  "company_id": "770e8400-e29b-41d4-a716-446655440000",
  "period_start": "2025-05-16",
  "period_end": "2025-05-31",
  "entries": [
    {
      "employee_id": "550e8400-e29b-41d4-a716-446655440000",
      "worked_minutes": 10080
    }
  ]
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `payroll_run_id` | string | Yes | 1–255 chars; used for idempotency |
| `company_id` | UUID | Yes | Company identifier |
| `period_start` | date | Yes | Pay period start |
| `period_end` | date | Yes | Pay period end; must be >= `period_start` |
| `entries` | array | Yes | At least one entry |
| `entries[].employee_id` | UUID | Yes | Employee identifier |
| `entries[].worked_minutes` | int | Yes | Minutes worked; must be > 0 |

**Response:** `200 OK`

```json
{
  "payroll_run_id": "PR-2025-06-01",
  "processed": 5,
  "accrued": 3,
  "skipped": 2,
  "errors": 0
}
```

**Idempotency:** Replaying the same `payroll_run_id` produces no duplicate ledger entries.

---

## Reports

### `GET /companies/{company_id}/audit-log`

Query audit log entries with optional filters.

**Auth:** Admin

**Query params:**

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `entity_type` | string | — | `POLICY`, `POLICY_VERSION`, `REQUEST`, `ASSIGNMENT`, `HOLIDAY`, `ADJUSTMENT`, `ACCRUAL` |
| `action` | string | — | `CREATE`, `UPDATE`, `DELETE`, `APPROVE`, `DENY`, `CANCEL`, `SUBMIT` |
| `actor_id` | UUID | — | Filter by who performed the action |
| `start_date` | date | — | Filter entries from this date |
| `end_date` | date | — | Filter entries up to this date |
| `offset` | int | 0 | Pagination offset |
| `limit` | int | 50 | Pagination limit (1–100) |

**Response:** `200 OK`

```json
{
  "items": [
    {
      "id": "...",
      "company_id": "...",
      "actor_id": "...",
      "entity_type": "REQUEST",
      "entity_id": "...",
      "action": "APPROVE",
      "before_json": { "status": "SUBMITTED" },
      "after_json": { "status": "APPROVED" },
      "created_at": "2025-06-01T14:30:00Z"
    }
  ],
  "total": 42
}
```

### `GET /companies/{company_id}/reports/balances`

Get a balance summary across all employees for a company.

**Auth:** Any

**Response:** `200 OK`

```json
{
  "items": [
    {
      "employee_id": "...",
      "policy_id": "...",
      "policy_key": "vacation-ft",
      "policy_category": "VACATION",
      "accrued_minutes": 9600,
      "used_minutes": 2400,
      "held_minutes": 0,
      "available_minutes": 7200,
      "is_unlimited": false
    }
  ],
  "total": 25
}
```

### `GET /companies/{company_id}/reports/ledger`

Export ledger entries with optional filters.

**Auth:** Admin

**Query params:**

| Parameter | Type | Default | Notes |
|-----------|------|---------|-------|
| `policy_id` | UUID | — | Filter by policy |
| `employee_id` | UUID | — | Filter by employee |
| `start_date` | date | — | Filter entries from this date |
| `end_date` | date | — | Filter entries up to this date |
| `offset` | int | 0 | Pagination offset |
| `limit` | int | 50 | Pagination limit (1–100) |

**Response:** `200 OK`

```json
{
  "items": [
    {
      "id": "...",
      "employee_id": "...",
      "policy_id": "...",
      "entry_type": "ACCRUAL",
      "amount_minutes": 800,
      "effective_at": "2025-06-01T00:00:00Z",
      "source_type": "SYSTEM",
      "source_id": "accrual:...",
      "metadata_json": { "frequency": "MONTHLY" },
      "created_at": "2025-06-01T00:00:01Z"
    }
  ],
  "total": 156
}
```

---

## Policy Settings

Policy settings use a discriminated union based on `type` and `accrual_method`. There are three variants:

### Unlimited

```json
{
  "type": "UNLIMITED",
  "unit": "DAYS"
}
```

### Time-Based Accrual

```json
{
  "type": "ACCRUAL",
  "accrual_method": "TIME",
  "unit": "DAYS",
  "accrual_frequency": "MONTHLY",
  "accrual_timing": "START_OF_PERIOD",
  "rate_minutes_per_year": 9600,
  "rate_minutes_per_month": null,
  "rate_minutes_per_day": null,
  "proration": "DAYS_ACTIVE",
  "allow_negative": false,
  "negative_limit_minutes": null,
  "bank_cap_minutes": 14400,
  "tenure_tiers": [
    { "min_months": 0, "accrual_rate_minutes": 9600 },
    { "min_months": 60, "accrual_rate_minutes": 11520 }
  ],
  "carryover": {
    "enabled": true,
    "cap_minutes": 4800,
    "expires_after_days": 90
  },
  "expiration": {
    "enabled": false
  }
}
```

| Field | Type | Notes |
|-------|------|-------|
| `accrual_frequency` | string | `DAILY`, `MONTHLY`, `YEARLY` |
| `accrual_timing` | string | `START_OF_PERIOD`, `END_OF_PERIOD` |
| `rate_minutes_per_year` | int | Set for YEARLY frequency |
| `rate_minutes_per_month` | int | Set for MONTHLY frequency |
| `rate_minutes_per_day` | int | Set for DAILY frequency |
| `proration` | string | `DAYS_ACTIVE` (prorate for mid-period joins) or `NONE` |
| `allow_negative` | bool | Allow balance to go below zero |
| `negative_limit_minutes` | int | Max negative balance (if `allow_negative=true`) |
| `bank_cap_minutes` | int | Maximum accrued balance |
| `tenure_tiers` | array | Rate overrides by employee tenure |
| `carryover` | object | Year-end carryover rules |
| `expiration` | object | Balance expiration rules |

Exactly one `rate_minutes_per_*` field must be set, matching the `accrual_frequency`.

### Hours-Worked Accrual

```json
{
  "type": "ACCRUAL",
  "accrual_method": "HOURS_WORKED",
  "unit": "HOURS",
  "accrual_ratio": {
    "accrue_minutes": 60,
    "per_worked_minutes": 1440
  },
  "allow_negative": false,
  "negative_limit_minutes": null,
  "bank_cap_minutes": null,
  "tenure_tiers": [],
  "carryover": { "enabled": false },
  "expiration": { "enabled": false }
}
```

`accrual_ratio` example: accrue 60 minutes (1 hour) for every 1440 minutes (24 hours) worked.

---

## Response Schemas

### PolicyResponse

```json
{
  "id": "UUID",
  "company_id": "UUID",
  "key": "vacation-ft",
  "category": "VACATION",
  "created_at": "datetime",
  "current_version": {
    "id": "UUID",
    "policy_id": "UUID",
    "version": 1,
    "effective_from": "date",
    "effective_to": null,
    "type": "ACCRUAL",
    "accrual_method": "TIME",
    "settings": { ... },
    "created_by": "UUID",
    "change_reason": "string | null",
    "created_at": "datetime"
  }
}
```

### AssignmentResponse

```json
{
  "id": "UUID",
  "company_id": "UUID",
  "employee_id": "UUID",
  "policy_id": "UUID",
  "effective_from": "date",
  "effective_to": "date | null",
  "created_by": "UUID",
  "created_at": "datetime"
}
```

### RequestResponse

```json
{
  "id": "UUID",
  "company_id": "UUID",
  "employee_id": "UUID",
  "policy_id": "UUID",
  "start_at": "datetime",
  "end_at": "datetime",
  "requested_minutes": 2400,
  "reason": "string | null",
  "status": "SUBMITTED",
  "submitted_at": "datetime | null",
  "decided_at": "datetime | null",
  "decided_by": "UUID | null",
  "decision_note": "string | null",
  "idempotency_key": "string | null",
  "created_at": "datetime"
}
```

### LedgerEntryResponse

```json
{
  "id": "UUID",
  "policy_id": "UUID",
  "policy_version_id": "UUID",
  "entry_type": "ACCRUAL",
  "amount_minutes": 800,
  "effective_at": "datetime",
  "source_type": "SYSTEM",
  "source_id": "accrual:...",
  "metadata_json": {},
  "created_at": "datetime"
}
```

### HolidayResponse

```json
{
  "id": "UUID",
  "company_id": "UUID",
  "date": "2025-12-25",
  "name": "Christmas Day"
}
```

### EmployeeResponse

```json
{
  "id": "UUID",
  "company_id": "UUID",
  "first_name": "Jane",
  "last_name": "Doe",
  "email": "jane.doe@example.com",
  "pay_type": "SALARY",
  "workday_minutes": 480,
  "timezone": "America/New_York",
  "hire_date": "2024-03-15"
}
```

---

## Enum Values

| Enum | Values |
|------|--------|
| PolicyCategory | `VACATION`, `SICK`, `PERSONAL`, `BEREAVEMENT`, `PARENTAL`, `OTHER` |
| PolicyType | `UNLIMITED`, `ACCRUAL` |
| AccrualMethod | `TIME`, `HOURS_WORKED` |
| AccrualFrequency | `DAILY`, `MONTHLY`, `YEARLY` |
| AccrualTiming | `START_OF_PERIOD`, `END_OF_PERIOD` |
| ProrationMethod | `DAYS_ACTIVE`, `NONE` |
| DisplayUnit | `MINUTES`, `HOURS`, `DAYS` |
| RequestStatus | `DRAFT`, `SUBMITTED`, `APPROVED`, `DENIED`, `CANCELLED` |
| LedgerEntryType | `ACCRUAL`, `HOLD`, `HOLD_RELEASE`, `USAGE`, `ADJUSTMENT`, `EXPIRATION`, `CARRYOVER` |
| LedgerSourceType | `REQUEST`, `PAYROLL`, `ADMIN`, `SYSTEM` |
| AuditEntityType | `POLICY`, `POLICY_VERSION`, `REQUEST`, `ASSIGNMENT`, `HOLIDAY`, `ADJUSTMENT`, `ACCRUAL` |
| AuditAction | `CREATE`, `UPDATE`, `DELETE`, `APPROVE`, `DENY`, `CANCEL`, `SUBMIT` |
