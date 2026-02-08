"""Seed script for development data.

Run with:  uv run python -m app.seed
Inside Docker:  docker compose exec api uv run python -m app.seed
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

BASE_URL = "http://localhost:8000"
COMPANY_ID = "00000000-0000-0000-0000-000000000001"
ADMIN_USER_ID = "00000000-0000-0000-0000-000000000001"

HEADERS = {
    "Content-Type": "application/json",
    "X-Company-Id": COMPANY_ID,
    "X-User-Id": ADMIN_USER_ID,
    "X-Role": "admin",
}

# Well-known employee UUIDs
ALICE_ID = "00000000-0000-0000-0000-000000000002"
BOB_ID = "00000000-0000-0000-0000-000000000003"
CAROL_ID = "00000000-0000-0000-0000-000000000004"
DAVE_ID = "00000000-0000-0000-0000-000000000005"

EMPLOYEES = [
    {
        "id": ALICE_ID,
        "first_name": "Alice",
        "last_name": "Johnson",
        "email": "alice.johnson@example.com",
        "pay_type": "SALARY",
        "workday_minutes": 480,
        "timezone": "America/New_York",
        "hire_date": "2023-01-15",
    },
    {
        "id": BOB_ID,
        "first_name": "Bob",
        "last_name": "Smith",
        "email": "bob.smith@example.com",
        "pay_type": "SALARY",
        "workday_minutes": 480,
        "timezone": "America/Chicago",
        "hire_date": "2023-06-01",
    },
    {
        "id": CAROL_ID,
        "first_name": "Carol",
        "last_name": "Williams",
        "email": "carol.williams@example.com",
        "pay_type": "HOURLY",
        "workday_minutes": 480,
        "timezone": "America/Los_Angeles",
        "hire_date": "2024-03-01",
    },
    {
        "id": DAVE_ID,
        "first_name": "Dave",
        "last_name": "Brown",
        "email": "dave.brown@example.com",
        "pay_type": "HOURLY",
        "workday_minutes": 360,
        "timezone": "America/Denver",
        "hire_date": "2024-09-15",
    },
]

POLICIES = [
    {
        "key": "unlimited-vacation",
        "category": "VACATION",
        "version": {
            "effective_from": "2024-01-01",
            "settings": {"type": "UNLIMITED", "unit": "DAYS"},
        },
    },
    {
        "key": "standard-pto",
        "category": "VACATION",
        "version": {
            "effective_from": "2024-01-01",
            "settings": {
                "type": "ACCRUAL",
                "accrual_method": "TIME",
                "unit": "DAYS",
                "accrual_frequency": "MONTHLY",
                "accrual_timing": "START_OF_PERIOD",
                "rate_minutes_per_month": 800,
                "rate_minutes_per_year": None,
                "rate_minutes_per_day": None,
                "proration": "DAYS_ACTIVE",
                "allow_negative": False,
                "negative_limit_minutes": None,
                "bank_cap_minutes": 19200,
                "tenure_tiers": [],
                "carryover": {"enabled": True, "cap_minutes": 4800, "expires_after_days": None},
                "expiration": {
                    "enabled": False,
                    "expires_after_days": None,
                    "expires_on_month": None,
                    "expires_on_day": None,
                },
            },
        },
    },
    {
        "key": "sick-leave",
        "category": "SICK",
        "version": {
            "effective_from": "2024-01-01",
            "settings": {
                "type": "ACCRUAL",
                "accrual_method": "TIME",
                "unit": "DAYS",
                "accrual_frequency": "YEARLY",
                "accrual_timing": "START_OF_PERIOD",
                "rate_minutes_per_year": 4800,
                "rate_minutes_per_month": None,
                "rate_minutes_per_day": None,
                "proration": "DAYS_ACTIVE",
                "allow_negative": False,
                "negative_limit_minutes": None,
                "bank_cap_minutes": 9600,
                "tenure_tiers": [],
                "carryover": {"enabled": False, "cap_minutes": None, "expires_after_days": None},
                "expiration": {
                    "enabled": False,
                    "expires_after_days": None,
                    "expires_on_month": None,
                    "expires_on_day": None,
                },
            },
        },
    },
    {
        "key": "hourly-pto",
        "category": "PERSONAL",
        "version": {
            "effective_from": "2024-01-01",
            "settings": {
                "type": "ACCRUAL",
                "accrual_method": "HOURS_WORKED",
                "unit": "HOURS",
                "accrual_ratio": {"accrue_minutes": 60, "per_worked_minutes": 1800},
                "allow_negative": False,
                "negative_limit_minutes": None,
                "bank_cap_minutes": 4800,
                "tenure_tiers": [],
                "carryover": {"enabled": False, "cap_minutes": None, "expires_after_days": None},
                "expiration": {
                    "enabled": False,
                    "expires_after_days": None,
                    "expires_on_month": None,
                    "expires_on_day": None,
                },
            },
        },
    },
]

HOLIDAYS = [
    {"date": "2026-01-01", "name": "New Year's Day"},
    {"date": "2026-01-19", "name": "Martin Luther King Jr. Day"},
    {"date": "2026-02-16", "name": "Presidents' Day"},
    {"date": "2026-05-25", "name": "Memorial Day"},
    {"date": "2026-07-03", "name": "Independence Day (Observed)"},
    {"date": "2026-09-07", "name": "Labor Day"},
]

# Assignments: (employee_id, policy_key)
ASSIGNMENTS = [
    (ALICE_ID, "unlimited-vacation"),
    (BOB_ID, "standard-pto"),
    (BOB_ID, "sick-leave"),
    (CAROL_ID, "standard-pto"),
    (CAROL_ID, "sick-leave"),
    (CAROL_ID, "hourly-pto"),
    (DAVE_ID, "hourly-pto"),
    (DAVE_ID, "sick-leave"),
]

# Adjustments: (employee_id, policy_key, amount_minutes, reason)
ADJUSTMENTS = [
    (BOB_ID, "standard-pto", 4800, "Initial PTO balance (10 days)"),
    (BOB_ID, "sick-leave", 2400, "Initial sick leave balance (5 days)"),
    (CAROL_ID, "standard-pto", 3200, "Initial PTO balance (6.67 days)"),
    (CAROL_ID, "sick-leave", 2400, "Initial sick leave balance (5 days)"),
    (DAVE_ID, "hourly-pto", 480, "Initial PTO balance (8 hours)"),
    (DAVE_ID, "sick-leave", 2400, "Initial sick leave balance (5 days)"),
]


async def _safe_post(client: httpx.AsyncClient, url: str, json: dict, label: str) -> dict | None:
    """POST with 409-conflict tolerance for idempotency."""
    resp = await client.post(url, json=json, headers=HEADERS)
    if resp.status_code in (200, 201):
        print(f"  [OK] {label}")
        return resp.json()
    if resp.status_code == 409:
        print(f"  [SKIP] {label} (already exists)")
        return None
    print(f"  [ERROR] {label}: {resp.status_code} {resp.text[:200]}")
    return None


async def _safe_put(client: httpx.AsyncClient, url: str, json: dict, label: str) -> dict | None:
    """PUT (upsert) — naturally idempotent."""
    resp = await client.put(url, json=json, headers=HEADERS)
    if resp.status_code in (200, 201):
        print(f"  [OK] {label}")
        return resp.json()
    print(f"  [ERROR] {label}: {resp.status_code} {resp.text[:200]}")
    return None


async def seed_employees(client: httpx.AsyncClient) -> None:
    """Seed employees via PUT (upsert)."""
    print("\n--- Seeding employees ---")
    for emp in EMPLOYEES:
        emp_id = emp["id"]
        body = {k: v for k, v in emp.items() if k != "id"}
        await _safe_put(
            client,
            f"{BASE_URL}/companies/{COMPANY_ID}/employees/{emp_id}",
            body,
            f"{emp['first_name']} {emp['last_name']}",
        )


async def seed_policies(client: httpx.AsyncClient) -> dict[str, str]:
    """Seed policies and return a key->id mapping."""
    print("\n--- Seeding policies ---")
    policy_ids: dict[str, str] = {}

    for policy_data in POLICIES:
        key = str(policy_data["key"])
        result = await _safe_post(
            client,
            f"{BASE_URL}/companies/{COMPANY_ID}/policies",
            policy_data,
            f"Policy: {key}",
        )
        if result:
            policy_ids[key] = result["id"]

    # If some policies already existed (409), fetch them by listing
    if len(policy_ids) < len(POLICIES):
        resp = await client.get(
            f"{BASE_URL}/companies/{COMPANY_ID}/policies",
            headers=HEADERS,
            params={"limit": 100},
        )
        if resp.status_code == 200:
            for item in resp.json().get("items", []):
                if item["key"] not in policy_ids:
                    policy_ids[item["key"]] = item["id"]

    return policy_ids


async def seed_assignments(client: httpx.AsyncClient, policy_ids: dict[str, str]) -> None:
    """Seed policy assignments."""
    print("\n--- Seeding assignments ---")
    for employee_id, policy_key in ASSIGNMENTS:
        pid = policy_ids.get(policy_key)
        if not pid:
            print(f"  [SKIP] {policy_key} not found for assignment")
            continue
        await _safe_post(
            client,
            f"{BASE_URL}/companies/{COMPANY_ID}/policies/{pid}/assignments",
            {"employee_id": employee_id, "effective_from": "2024-01-01"},
            f"Assign {employee_id[:12]}... -> {policy_key}",
        )


async def seed_holidays(client: httpx.AsyncClient) -> None:
    """Seed company holidays."""
    print("\n--- Seeding holidays ---")
    for holiday in HOLIDAYS:
        await _safe_post(
            client,
            f"{BASE_URL}/companies/{COMPANY_ID}/holidays",
            holiday,
            f"Holiday: {holiday['name']}",
        )


async def _get_employee_balance(client: httpx.AsyncClient, employee_id: str, policy_id: str) -> int:
    """Get current accrued_minutes for an employee+policy, or 0 if not found."""
    resp = await client.get(
        f"{BASE_URL}/companies/{COMPANY_ID}/employees/{employee_id}/balances",
        headers=HEADERS,
    )
    if resp.status_code != 200:
        return 0
    for item in resp.json().get("items", []):
        if item["policy_id"] == policy_id:
            return item.get("accrued_minutes", 0)
    return 0


async def seed_adjustments(client: httpx.AsyncClient, policy_ids: dict[str, str]) -> None:
    """Seed balance adjustments (skip if employee already has balance)."""
    print("\n--- Seeding adjustments ---")
    for employee_id, policy_key, amount, reason in ADJUSTMENTS:
        pid = policy_ids.get(policy_key)
        if not pid:
            print(f"  [SKIP] {policy_key} not found for adjustment")
            continue

        existing = await _get_employee_balance(client, employee_id, pid)
        if existing > 0:
            print(f"  [SKIP] {employee_id[:12]}... {policy_key} (balance already {existing}m)")
            continue

        await _safe_post(
            client,
            f"{BASE_URL}/companies/{COMPANY_ID}/adjustments",
            {
                "employee_id": employee_id,
                "policy_id": pid,
                "amount_minutes": amount,
                "reason": reason,
            },
            f"Adjust {employee_id[:12]}... {policy_key} +{amount}m",
        )


def _next_business_day(start: datetime, tz: ZoneInfo, days_ahead: int = 1) -> datetime:
    """Find a business day (Mon-Fri) at least days_ahead days from start in the given tz."""
    local = start.astimezone(tz)
    candidate = local + timedelta(days=days_ahead)
    while candidate.weekday() >= 5:  # Skip weekends
        candidate += timedelta(days=1)
    return candidate


async def seed_requests(client: httpx.AsyncClient, policy_ids: dict[str, str]) -> None:
    """Seed time-off requests."""
    print("\n--- Seeding requests ---")
    now = datetime.now(UTC)

    # Request 1: Bob — 3 days standard-pto, future, stays SUBMITTED
    # Bob is in America/Chicago — construct times in his timezone
    bob_tz = ZoneInfo("America/Chicago")
    bob_day = _next_business_day(now, bob_tz, days_ahead=7)
    bob_start = bob_day.replace(hour=9, minute=0, second=0, microsecond=0)
    # Find 2 more business days after bob_start for a 3-day request
    bob_end_day = _next_business_day(bob_start, bob_tz, days_ahead=2)
    while bob_end_day.weekday() >= 5:
        bob_end_day += timedelta(days=1)
    bob_end = bob_end_day.replace(hour=17, minute=0, second=0, microsecond=0)

    standard_pto_id = policy_ids.get("standard-pto")
    if standard_pto_id:
        await _safe_post(
            client,
            f"{BASE_URL}/companies/{COMPANY_ID}/requests",
            {
                "employee_id": BOB_ID,
                "policy_id": standard_pto_id,
                "start_at": bob_start.isoformat(),
                "end_at": bob_end.isoformat(),
                "reason": "Family vacation",
                "idempotency_key": "seed-bob-pto-req",
            },
            "Request: Bob 3-day vacation (SUBMITTED)",
        )

    # Request 2: Carol — 1 day sick-leave, past weekday, then APPROVE it
    # Carol is in America/Los_Angeles
    carol_tz = ZoneInfo("America/Los_Angeles")
    # Go back 10 days and find a weekday
    carol_day = now.astimezone(carol_tz) - timedelta(days=10)
    while carol_day.weekday() >= 5:
        carol_day -= timedelta(days=1)
    carol_start = carol_day.replace(hour=9, minute=0, second=0, microsecond=0)
    carol_end = carol_day.replace(hour=17, minute=0, second=0, microsecond=0)

    sick_id = policy_ids.get("sick-leave")
    if sick_id:
        result = await _safe_post(
            client,
            f"{BASE_URL}/companies/{COMPANY_ID}/requests",
            {
                "employee_id": CAROL_ID,
                "policy_id": sick_id,
                "start_at": carol_start.isoformat(),
                "end_at": carol_end.isoformat(),
                "reason": "Doctor appointment",
                "idempotency_key": "seed-carol-sick-req",
            },
            "Request: Carol 1-day sick leave",
        )
        if result:
            req_id = result["id"]
            resp = await client.post(
                f"{BASE_URL}/companies/{COMPANY_ID}/requests/{req_id}/approve",
                json={"note": "Approved — feel better!"},
                headers=HEADERS,
            )
            if resp.status_code == 200:
                print("  [OK] Approved Carol's sick leave request")
            elif resp.status_code == 400:
                print("  [SKIP] Carol's request already decided")
            else:
                print(f"  [ERROR] Approving Carol's request: {resp.status_code}")

    # Request 3: Dave — 4 hours hourly-pto, future weekday, stays SUBMITTED
    # Dave is in America/Denver
    dave_tz = ZoneInfo("America/Denver")
    dave_day = _next_business_day(now, dave_tz, days_ahead=14)
    dave_start = dave_day.replace(hour=9, minute=0, second=0, microsecond=0)
    dave_end = dave_day.replace(hour=13, minute=0, second=0, microsecond=0)

    hourly_id = policy_ids.get("hourly-pto")
    if hourly_id:
        await _safe_post(
            client,
            f"{BASE_URL}/companies/{COMPANY_ID}/requests",
            {
                "employee_id": DAVE_ID,
                "policy_id": hourly_id,
                "start_at": dave_start.isoformat(),
                "end_at": dave_end.isoformat(),
                "reason": "Personal errand",
                "idempotency_key": "seed-dave-hourly-req",
            },
            "Request: Dave 4-hour personal (SUBMITTED)",
        )


async def main() -> None:
    print("=" * 60)
    print("  Power PTO — Development Seed Script")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Health check
        try:
            resp = await client.get(f"{BASE_URL}/health")
            if resp.status_code != 200:
                print(f"API health check failed: {resp.status_code}")
                sys.exit(1)
            print("\n[OK] API is healthy")
        except httpx.ConnectError:
            print("ERROR: Cannot connect to API at", BASE_URL)
            print("Make sure the API is running (make up)")
            sys.exit(1)

        await seed_employees(client)
        policy_ids = await seed_policies(client)
        await seed_assignments(client, policy_ids)
        await seed_holidays(client)
        await seed_adjustments(client, policy_ids)
        await seed_requests(client, policy_ids)

    print("\n" + "=" * 60)
    print("  Seeding complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
