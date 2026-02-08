"""Comprehensive tests for carryover and expiration processing.

Covers year-end carryover with caps, no caps, use-it-or-lose-it,
idempotency, date gating, zero-balance skip, admin-only access,
calendar-date expiration, carryover-days expiration, and expiration
idempotency.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

import pytest

from app.services.employee import EmployeeInfo, InMemoryEmployeeService, set_employee_service

if TYPE_CHECKING:
    from collections.abc import Iterator

    from httpx import AsyncClient

COMPANY_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
EMPLOYEE_ID = uuid.uuid4()

AUTH_HEADERS = {
    "X-Company-Id": str(COMPANY_ID),
    "X-User-Id": str(USER_ID),
    "X-Role": "admin",
}
EMPLOYEE_HEADERS = {
    "X-Company-Id": str(COMPANY_ID),
    "X-User-Id": str(USER_ID),
    "X-Role": "employee",
}

POLICIES_URL = f"/companies/{COMPANY_ID}/policies"
TRIGGER_URL = f"/companies/{COMPANY_ID}/accruals/trigger"
CARRYOVER_URL = f"/companies/{COMPANY_ID}/accruals/carryover"
EXPIRATION_URL = f"/companies/{COMPANY_ID}/accruals/expiration"
BALANCES_URL = f"/companies/{COMPANY_ID}/employees/{EMPLOYEE_ID}/balances"
LEDGER_URL = f"/companies/{COMPANY_ID}/employees/{EMPLOYEE_ID}/ledger"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _seed_employee_service() -> Iterator[None]:
    """Seed the in-memory employee service for every test."""
    svc = InMemoryEmployeeService()
    svc.seed(
        EmployeeInfo(
            id=EMPLOYEE_ID,
            company_id=COMPANY_ID,
            first_name="Test",
            last_name="Employee",
            email="test@example.com",
            pay_type="SALARY",
            workday_minutes=480,
            timezone="America/New_York",
            hire_date=date(2024, 1, 1),
        )
    )
    set_employee_service(svc)
    yield
    set_employee_service(InMemoryEmployeeService())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_policy_with_carryover(
    client: AsyncClient,
    key: str = "vacation-accrual",
    rate_minutes_per_day: int = 40,
    cap_minutes: int | None = 960,
    expires_after_days: int | None = 90,
    expiration_enabled: bool = False,
    expires_on_month: int | None = None,
    expires_on_day: int | None = None,
) -> str:
    """Create a daily-accrual policy with carryover and/or expiration settings.

    Returns the policy ID.
    """
    settings: dict[str, Any] = {
        "type": "ACCRUAL",
        "accrual_method": "TIME",
        "accrual_frequency": "DAILY",
        "accrual_timing": "START_OF_PERIOD",
        "rate_minutes_per_day": rate_minutes_per_day,
        "carryover": {
            "enabled": True,
            "cap_minutes": cap_minutes,
            "expires_after_days": expires_after_days,
        },
        "expiration": {
            "enabled": expiration_enabled,
            "expires_on_month": expires_on_month,
            "expires_on_day": expires_on_day,
        },
    }
    resp = await client.post(
        POLICIES_URL,
        json={
            "key": key,
            "category": "VACATION",
            "version": {"effective_from": "2025-01-01", "settings": settings},
        },
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201
    policy_id: str = resp.json()["id"]
    return policy_id


async def _assign_employee(
    client: AsyncClient,
    policy_id: str,
    effective_from: str = "2025-01-01",
) -> str:
    """Assign EMPLOYEE_ID to the given policy and return assignment ID."""
    resp = await client.post(
        f"{POLICIES_URL}/{policy_id}/assignments",
        json={"employee_id": str(EMPLOYEE_ID), "effective_from": effective_from},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201
    assignment_id: str = resp.json()["id"]
    return assignment_id


async def _setup_policy_with_carryover(
    client: AsyncClient,
    key: str = "vacation-accrual",
    rate_minutes_per_day: int = 40,
    cap_minutes: int | None = 960,
    expires_after_days: int | None = 90,
    expiration_enabled: bool = False,
    expires_on_month: int | None = None,
    expires_on_day: int | None = None,
) -> str:
    """Create a policy with carryover and assign EMPLOYEE_ID to it.

    Returns the policy ID.
    """
    pid = await _create_policy_with_carryover(
        client,
        key=key,
        rate_minutes_per_day=rate_minutes_per_day,
        cap_minutes=cap_minutes,
        expires_after_days=expires_after_days,
        expiration_enabled=expiration_enabled,
        expires_on_month=expires_on_month,
        expires_on_day=expires_on_day,
    )
    await _assign_employee(client, pid)
    return pid


async def _accrue_days(
    client: AsyncClient,
    n_days: int,
    start_date: date = date(2025, 1, 1),
) -> None:
    """Trigger daily accrual for n_days starting from start_date."""
    for i in range(n_days):
        d = start_date + timedelta(days=i)
        await client.post(
            TRIGGER_URL,
            params={"target_date": str(d)},
            headers=AUTH_HEADERS,
        )


async def _get_balance(client: AsyncClient, policy_id: str) -> dict[str, Any]:
    """Fetch the balance for EMPLOYEE_ID and return the item matching the policy."""
    resp = await client.get(BALANCES_URL, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    balance: dict[str, Any] = next(b for b in resp.json()["items"] if b["policy_id"] == policy_id)
    return balance


# ===========================================================================
# Carryover tests
# ===========================================================================


class TestCarryoverWithCap:
    """Accrual balance exceeds carryover cap -> cap applied, excess expired."""

    async def test_carryover_with_cap(self, async_client: AsyncClient) -> None:
        """Accrue 2000 min with cap 960 -> carries 960, expires 1040."""
        pid = await _setup_policy_with_carryover(
            async_client,
            key="co-cap-1",
            rate_minutes_per_day=40,
            cap_minutes=960,
            expires_after_days=90,
        )

        # Accrue 50 days of daily accrual (40 min/day = 2000 min total)
        await _accrue_days(async_client, 50, start_date=date(2025, 1, 1))

        # Verify we accrued 2000 minutes
        balance = await _get_balance(async_client, pid)
        assert balance["accrued_minutes"] == 2000

        # Trigger carryover on Jan 1 2026
        resp = await async_client.post(
            CARRYOVER_URL,
            params={"target_date": "2026-01-01"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["carryovers_processed"] == 1
        assert data["expirations_processed"] == 1

        # After carryover: accrued should be reduced by the expired 1040
        balance = await _get_balance(async_client, pid)
        assert balance["accrued_minutes"] == 960
        assert balance["available_minutes"] == 960


class TestCarryoverNoCap:
    """No cap_minutes -> all balance carries over, nothing expires."""

    async def test_carryover_no_cap(self, async_client: AsyncClient) -> None:
        pid = await _setup_policy_with_carryover(
            async_client,
            key="co-nocap-1",
            rate_minutes_per_day=40,
            cap_minutes=None,
            expires_after_days=90,
        )

        # Accrue 50 days = 2000 min
        await _accrue_days(async_client, 50, start_date=date(2025, 1, 1))

        balance = await _get_balance(async_client, pid)
        assert balance["accrued_minutes"] == 2000

        # Trigger carryover on Jan 1 2026
        resp = await async_client.post(
            CARRYOVER_URL,
            params={"target_date": "2026-01-01"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["carryovers_processed"] == 1
        # No cap, so no expiration during carryover
        assert data["expirations_processed"] == 0

        # Balance unchanged: all carried over
        balance = await _get_balance(async_client, pid)
        assert balance["accrued_minutes"] == 2000
        assert balance["available_minutes"] == 2000


class TestCarryoverUseItOrLoseIt:
    """cap_minutes=0 -> everything expires (use-it-or-lose-it)."""

    async def test_carryover_use_it_or_lose_it(self, async_client: AsyncClient) -> None:
        pid = await _setup_policy_with_carryover(
            async_client,
            key="co-uioli-1",
            rate_minutes_per_day=40,
            cap_minutes=0,
            expires_after_days=None,
        )

        # Accrue 50 days = 2000 min
        await _accrue_days(async_client, 50, start_date=date(2025, 1, 1))

        balance = await _get_balance(async_client, pid)
        assert balance["accrued_minutes"] == 2000

        # Trigger carryover on Jan 1 2026
        resp = await async_client.post(
            CARRYOVER_URL,
            params={"target_date": "2026-01-01"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["carryovers_processed"] == 1
        assert data["expirations_processed"] == 1

        # Everything expired
        balance = await _get_balance(async_client, pid)
        assert balance["accrued_minutes"] == 0
        assert balance["available_minutes"] == 0


class TestCarryoverIdempotent:
    """Running carryover twice for the same date produces the same result."""

    async def test_carryover_idempotent(self, async_client: AsyncClient) -> None:
        pid = await _setup_policy_with_carryover(
            async_client,
            key="co-idem-1",
            rate_minutes_per_day=40,
            cap_minutes=960,
            expires_after_days=90,
        )

        # Accrue 50 days = 2000 min
        await _accrue_days(async_client, 50, start_date=date(2025, 1, 1))

        # First carryover
        resp1 = await async_client.post(
            CARRYOVER_URL,
            params={"target_date": "2026-01-01"},
            headers=AUTH_HEADERS,
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["carryovers_processed"] == 1

        balance_after_first = await _get_balance(async_client, pid)

        # Second carryover (should be idempotent)
        resp2 = await async_client.post(
            CARRYOVER_URL,
            params={"target_date": "2026-01-01"},
            headers=AUTH_HEADERS,
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        # Already processed -> skipped
        assert data2["carryovers_processed"] == 0
        assert data2["skipped"] >= 1

        # Balance unchanged
        balance_after_second = await _get_balance(async_client, pid)
        assert balance_after_second["accrued_minutes"] == balance_after_first["accrued_minutes"]
        assert balance_after_second["available_minutes"] == balance_after_first["available_minutes"]


class TestCarryoverOnlyOnJan1:
    """Carryover for a non-Jan-1 date returns zero processed."""

    async def test_carryover_only_on_jan_1(self, async_client: AsyncClient) -> None:
        await _setup_policy_with_carryover(
            async_client,
            key="co-notjan1-1",
            rate_minutes_per_day=40,
            cap_minutes=960,
        )

        # Accrue some balance
        await _accrue_days(async_client, 10, start_date=date(2025, 1, 1))

        # Trigger carryover on June 15 (not Jan 1) -> should return zero processed
        resp = await async_client.post(
            CARRYOVER_URL,
            params={"target_date": "2026-06-15"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["carryovers_processed"] == 0
        assert data["expirations_processed"] == 0


class TestCarryoverSkipsZeroBalance:
    """No accruals (zero balance) -> carryover is skipped."""

    async def test_carryover_skips_zero_balance(self, async_client: AsyncClient) -> None:
        await _setup_policy_with_carryover(
            async_client,
            key="co-zero-1",
            rate_minutes_per_day=40,
            cap_minutes=960,
        )

        # Do NOT accrue any balance

        resp = await async_client.post(
            CARRYOVER_URL,
            params={"target_date": "2026-01-01"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["carryovers_processed"] == 0
        assert data["expirations_processed"] == 0
        assert data["skipped"] >= 1


class TestCarryoverAdminOnly:
    """Employee role cannot trigger carryover."""

    async def test_carryover_admin_only(self, async_client: AsyncClient) -> None:
        resp = await async_client.post(
            CARRYOVER_URL,
            params={"target_date": "2026-01-01"},
            headers=EMPLOYEE_HEADERS,
        )
        assert resp.status_code == 403


# ===========================================================================
# Expiration tests
# ===========================================================================


class TestCalendarDateExpiration:
    """Calendar-date expiration: entire balance expires on configured month/day."""

    async def test_calendar_date_expiration(self, async_client: AsyncClient) -> None:
        """Expiration enabled with expires_on 06-30 -> balance expires on June 30."""
        pid = await _setup_policy_with_carryover(
            async_client,
            key="exp-cal-1",
            rate_minutes_per_day=40,
            cap_minutes=None,
            expires_after_days=None,
            expiration_enabled=True,
            expires_on_month=6,
            expires_on_day=30,
        )

        # Accrue 30 days = 1200 min
        await _accrue_days(async_client, 30, start_date=date(2025, 1, 1))

        balance = await _get_balance(async_client, pid)
        assert balance["accrued_minutes"] == 1200

        # Trigger expiration on June 30
        resp = await async_client.post(
            EXPIRATION_URL,
            params={"target_date": "2025-06-30"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["expirations_processed"] == 1

        # Balance should be expired to zero
        balance = await _get_balance(async_client, pid)
        assert balance["accrued_minutes"] == 0
        assert balance["available_minutes"] == 0


class TestCalendarDateExpirationWrongDate:
    """Triggering expiration on a non-matching date -> nothing expires."""

    async def test_calendar_date_expiration_wrong_date(self, async_client: AsyncClient) -> None:
        pid = await _setup_policy_with_carryover(
            async_client,
            key="exp-wrong-1",
            rate_minutes_per_day=40,
            cap_minutes=None,
            expires_after_days=None,
            expiration_enabled=True,
            expires_on_month=6,
            expires_on_day=30,
        )

        # Accrue 30 days = 1200 min
        await _accrue_days(async_client, 30, start_date=date(2025, 1, 1))

        balance_before = await _get_balance(async_client, pid)
        assert balance_before["accrued_minutes"] == 1200

        # Trigger on a non-matching date (July 15 instead of June 30)
        resp = await async_client.post(
            EXPIRATION_URL,
            params={"target_date": "2025-07-15"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["expirations_processed"] == 0

        # Balance unchanged
        balance_after = await _get_balance(async_client, pid)
        assert balance_after["accrued_minutes"] == 1200
        assert balance_after["available_minutes"] == 1200


class TestCarryoverExpirationAfterDays:
    """Carried-over balance expires N days after Jan 1."""

    async def test_carryover_expiration_after_days(self, async_client: AsyncClient) -> None:
        """expires_after_days=90 -> trigger on April 1 (90 days after Jan 1) expires carried amount."""
        pid = await _setup_policy_with_carryover(
            async_client,
            key="exp-days-1",
            rate_minutes_per_day=40,
            cap_minutes=960,
            expires_after_days=90,
        )

        # Accrue 50 days = 2000 min
        await _accrue_days(async_client, 50, start_date=date(2025, 1, 1))

        balance = await _get_balance(async_client, pid)
        assert balance["accrued_minutes"] == 2000

        # Step 1: Run carryover on Jan 1 2026 -> carries 960, expires 1040
        resp = await async_client.post(
            CARRYOVER_URL,
            params={"target_date": "2026-01-01"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["carryovers_processed"] == 1

        balance = await _get_balance(async_client, pid)
        assert balance["accrued_minutes"] == 960

        # Step 2: Trigger expiration on April 1 (90 days after Jan 1 = April 1)
        resp = await async_client.post(
            EXPIRATION_URL,
            params={"target_date": "2026-04-01"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["expirations_processed"] == 1

        # The carried 960 minutes should now be expired
        balance = await _get_balance(async_client, pid)
        assert balance["accrued_minutes"] == 0
        assert balance["available_minutes"] == 0


class TestExpirationIdempotent:
    """Running expiration twice for the same date produces the same result."""

    async def test_expiration_idempotent(self, async_client: AsyncClient) -> None:
        pid = await _setup_policy_with_carryover(
            async_client,
            key="exp-idem-1",
            rate_minutes_per_day=40,
            cap_minutes=None,
            expires_after_days=None,
            expiration_enabled=True,
            expires_on_month=6,
            expires_on_day=30,
        )

        # Accrue 30 days = 1200 min
        await _accrue_days(async_client, 30, start_date=date(2025, 1, 1))

        # First expiration
        resp1 = await async_client.post(
            EXPIRATION_URL,
            params={"target_date": "2025-06-30"},
            headers=AUTH_HEADERS,
        )
        assert resp1.status_code == 200
        assert resp1.json()["expirations_processed"] == 1

        balance_after_first = await _get_balance(async_client, pid)
        assert balance_after_first["accrued_minutes"] == 0

        # Second expiration (should be idempotent)
        resp2 = await async_client.post(
            EXPIRATION_URL,
            params={"target_date": "2025-06-30"},
            headers=AUTH_HEADERS,
        )
        assert resp2.status_code == 200
        # Already processed -> skipped (or zero balance skip)
        assert resp2.json()["expirations_processed"] == 0

        # Balance unchanged
        balance_after_second = await _get_balance(async_client, pid)
        assert balance_after_second["accrued_minutes"] == balance_after_first["accrued_minutes"]
        assert balance_after_second["available_minutes"] == balance_after_first["available_minutes"]
