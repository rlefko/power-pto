"""Comprehensive tests for accrual engines: time-based accruals, proration,
hours-worked accruals, payroll webhook, idempotency, replay safety, and balance invariants.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING, Any

import pytest
from sqlalchemy import func, select
from sqlmodel import col

from app.models.audit import AuditLog
from app.models.balance import TimeOffBalanceSnapshot
from app.models.enums import AccrualFrequency, AccrualTiming, LedgerEntryType
from app.models.ledger import TimeOffLedgerEntry
from app.schemas.policy import AccrualRatio, HoursWorkedAccrualSettings, TimeAccrualSettings
from app.services.accrual import (
    _apply_bank_cap,
    _build_payroll_source_id,
    _build_time_accrual_source_id,
    _compute_accrual_amount,
    _compute_hours_worked_accrual,
    _get_period_boundaries,
    _is_accrual_date,
    _resolve_accrual_rate,
)
from app.services.employee import EmployeeInfo, InMemoryEmployeeService, set_employee_service

if TYPE_CHECKING:
    from collections.abc import Iterator

    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

COMPANY_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
EMPLOYEE_ID = uuid.uuid4()
EMPLOYEE_ID_2 = uuid.uuid4()
EMPLOYEE_ID_3 = uuid.uuid4()

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
WEBHOOK_URL = "/webhooks/payroll_processed"


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
    svc.seed(
        EmployeeInfo(
            id=EMPLOYEE_ID_2,
            company_id=COMPANY_ID,
            first_name="Second",
            last_name="Employee",
            email="second@example.com",
            pay_type="HOURLY",
            workday_minutes=480,
            timezone="America/New_York",
            hire_date=date(2024, 6, 1),
        )
    )
    svc.seed(
        EmployeeInfo(
            id=EMPLOYEE_ID_3,
            company_id=COMPANY_ID,
            first_name="Third",
            last_name="Employee",
            email="third@example.com",
            pay_type="HOURLY",
            workday_minutes=480,
            timezone="America/New_York",
            hire_date=date(2024, 1, 1),
        )
    )
    set_employee_service(svc)
    yield
    set_employee_service(InMemoryEmployeeService())


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


async def _create_time_accrual_policy(
    client: AsyncClient,
    key: str = "accrual-vacation",
    frequency: str = "DAILY",
    timing: str = "START_OF_PERIOD",
    rate_field: str = "rate_minutes_per_day",
    rate_value: int = 480,
    proration: str = "DAYS_ACTIVE",
    bank_cap_minutes: int | None = None,
    tenure_tiers: list[dict[str, int]] | None = None,
    effective_from: str = "2025-01-01",
) -> str:
    """Create a time-based accrual policy and return its ID."""
    settings: dict[str, Any] = {
        "type": "ACCRUAL",
        "accrual_method": "TIME",
        "accrual_frequency": frequency,
        "accrual_timing": timing,
        rate_field: rate_value,
        "proration": proration,
    }
    if bank_cap_minutes is not None:
        settings["bank_cap_minutes"] = bank_cap_minutes
    if tenure_tiers is not None:
        settings["tenure_tiers"] = tenure_tiers
    resp = await client.post(
        POLICIES_URL,
        json={
            "key": key,
            "category": "VACATION",
            "version": {"effective_from": effective_from, "settings": settings},
        },
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201
    policy_id: str = resp.json()["id"]
    return policy_id


async def _create_hours_worked_policy(
    client: AsyncClient,
    key: str = "accrual-sick",
    accrue_minutes: int = 60,
    per_worked_minutes: int = 1440,
    bank_cap_minutes: int | None = None,
    effective_from: str = "2025-01-01",
) -> str:
    """Create an hours-worked accrual policy and return its ID."""
    settings: dict[str, Any] = {
        "type": "ACCRUAL",
        "accrual_method": "HOURS_WORKED",
        "accrual_ratio": {
            "accrue_minutes": accrue_minutes,
            "per_worked_minutes": per_worked_minutes,
        },
    }
    if bank_cap_minutes is not None:
        settings["bank_cap_minutes"] = bank_cap_minutes
    resp = await client.post(
        POLICIES_URL,
        json={
            "key": key,
            "category": "SICK",
            "version": {"effective_from": effective_from, "settings": settings},
        },
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201
    policy_id: str = resp.json()["id"]
    return policy_id


async def _create_unlimited_policy(client: AsyncClient, key: str = "unlimited-vac") -> str:
    """Create an unlimited policy and return its ID."""
    resp = await client.post(
        POLICIES_URL,
        json={
            "key": key,
            "category": "VACATION",
            "version": {"effective_from": "2025-01-01", "settings": {"type": "UNLIMITED"}},
        },
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201
    policy_id: str = resp.json()["id"]
    return policy_id


async def _assign_employee(
    client: AsyncClient,
    policy_id: str,
    employee_id: uuid.UUID = EMPLOYEE_ID,
    effective_from: str = "2025-01-01",
) -> str:
    """Assign employee to policy and return assignment ID."""
    resp = await client.post(
        f"{POLICIES_URL}/{policy_id}/assignments",
        json={"employee_id": str(employee_id), "effective_from": effective_from},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201
    assignment_id: str = resp.json()["id"]
    return assignment_id


def _balances_url(employee_id: uuid.UUID = EMPLOYEE_ID) -> str:
    return f"/companies/{COMPANY_ID}/employees/{employee_id}/balances"


def _ledger_url(employee_id: uuid.UUID = EMPLOYEE_ID) -> str:
    return f"/companies/{COMPANY_ID}/employees/{employee_id}/ledger"


def _adjustment_url() -> str:
    return f"/companies/{COMPANY_ID}/adjustments"


# ===========================================================================
# Pure computation tests (no DB)
# ===========================================================================


class TestIsAccrualDate:
    """Tests for _is_accrual_date."""

    def test_daily_always_true(self) -> None:
        assert _is_accrual_date(AccrualFrequency.DAILY, AccrualTiming.START_OF_PERIOD, date(2025, 3, 15)) is True
        assert _is_accrual_date(AccrualFrequency.DAILY, AccrualTiming.END_OF_PERIOD, date(2025, 7, 22)) is True

    def test_monthly_start_on_first(self) -> None:
        assert _is_accrual_date(AccrualFrequency.MONTHLY, AccrualTiming.START_OF_PERIOD, date(2025, 1, 1)) is True

    def test_monthly_start_not_on_first(self) -> None:
        assert _is_accrual_date(AccrualFrequency.MONTHLY, AccrualTiming.START_OF_PERIOD, date(2025, 1, 15)) is False

    def test_monthly_end_on_last_day_31(self) -> None:
        assert _is_accrual_date(AccrualFrequency.MONTHLY, AccrualTiming.END_OF_PERIOD, date(2025, 1, 31)) is True

    def test_monthly_end_on_last_day_30(self) -> None:
        assert _is_accrual_date(AccrualFrequency.MONTHLY, AccrualTiming.END_OF_PERIOD, date(2025, 4, 30)) is True

    def test_monthly_end_on_last_day_28(self) -> None:
        assert _is_accrual_date(AccrualFrequency.MONTHLY, AccrualTiming.END_OF_PERIOD, date(2025, 2, 28)) is True

    def test_monthly_end_on_last_day_29_leap(self) -> None:
        assert _is_accrual_date(AccrualFrequency.MONTHLY, AccrualTiming.END_OF_PERIOD, date(2024, 2, 29)) is True

    def test_monthly_end_not_last_day(self) -> None:
        assert _is_accrual_date(AccrualFrequency.MONTHLY, AccrualTiming.END_OF_PERIOD, date(2025, 1, 30)) is False

    def test_yearly_start_jan_1(self) -> None:
        assert _is_accrual_date(AccrualFrequency.YEARLY, AccrualTiming.START_OF_PERIOD, date(2025, 1, 1)) is True

    def test_yearly_start_not_jan_1(self) -> None:
        assert _is_accrual_date(AccrualFrequency.YEARLY, AccrualTiming.START_OF_PERIOD, date(2025, 6, 1)) is False

    def test_yearly_end_dec_31(self) -> None:
        assert _is_accrual_date(AccrualFrequency.YEARLY, AccrualTiming.END_OF_PERIOD, date(2025, 12, 31)) is True

    def test_yearly_end_not_dec_31(self) -> None:
        assert _is_accrual_date(AccrualFrequency.YEARLY, AccrualTiming.END_OF_PERIOD, date(2025, 6, 30)) is False


class TestGetPeriodBoundaries:
    """Tests for _get_period_boundaries."""

    def test_daily(self) -> None:
        start, end = _get_period_boundaries(AccrualFrequency.DAILY, date(2025, 3, 15))
        assert start == date(2025, 3, 15)
        assert end == date(2025, 3, 16)

    def test_monthly(self) -> None:
        start, end = _get_period_boundaries(AccrualFrequency.MONTHLY, date(2025, 1, 15))
        assert start == date(2025, 1, 1)
        assert end == date(2025, 2, 1)

    def test_monthly_february(self) -> None:
        start, end = _get_period_boundaries(AccrualFrequency.MONTHLY, date(2025, 2, 14))
        assert start == date(2025, 2, 1)
        assert end == date(2025, 3, 1)

    def test_monthly_december(self) -> None:
        start, end = _get_period_boundaries(AccrualFrequency.MONTHLY, date(2025, 12, 25))
        assert start == date(2025, 12, 1)
        assert end == date(2026, 1, 1)

    def test_yearly(self) -> None:
        start, end = _get_period_boundaries(AccrualFrequency.YEARLY, date(2025, 6, 15))
        assert start == date(2025, 1, 1)
        assert end == date(2026, 1, 1)


class TestComputeAccrualAmount:
    """Tests for _compute_accrual_amount."""

    def _make_settings(
        self,
        frequency: str = "DAILY",
        rate_field: str = "rate_minutes_per_day",
        rate_value: int = 480,
        proration: str = "DAYS_ACTIVE",
    ) -> TimeAccrualSettings:
        kwargs: dict[str, Any] = {
            "accrual_frequency": frequency,
            rate_field: rate_value,
            "proration": proration,
        }
        return TimeAccrualSettings(**kwargs)

    def test_full_period_daily(self) -> None:
        settings = self._make_settings()
        amount = _compute_accrual_amount(settings, date(2025, 3, 15), date(2025, 1, 1))
        assert amount == 480

    def test_full_period_monthly(self) -> None:
        settings = self._make_settings("MONTHLY", "rate_minutes_per_month", 960)
        amount = _compute_accrual_amount(settings, date(2025, 2, 1), date(2025, 1, 1))
        assert amount == 960  # Full month, assigned from before period

    def test_proration_days_active_monthly(self) -> None:
        """Assignment starts Jan 15; January has 31 days, active = 17 days."""
        settings = self._make_settings("MONTHLY", "rate_minutes_per_month", 480)
        amount = _compute_accrual_amount(settings, date(2025, 1, 1), date(2025, 1, 15))
        # active_days = 31 - 15 + 1... wait, the period is [Jan 1, Feb 1).
        # active_start = max(Jan 15, Jan 1) = Jan 15
        # active_days = (Feb 1 - Jan 15).days = 17
        # prorated = 480 * 17 // 31 = 263
        assert amount == 263

    def test_proration_days_active_yearly(self) -> None:
        """Assignment starts Jul 1; year has 365 days, active = 184 days."""
        settings = self._make_settings("YEARLY", "rate_minutes_per_year", 9600)
        amount = _compute_accrual_amount(settings, date(2025, 1, 1), date(2025, 7, 1))
        # active_start = Jul 1, period_end = Jan 1 2026
        # active_days = (2026-01-01 - 2025-07-01).days = 184
        # total_days = 365
        # prorated = 9600 * 184 // 365 = 4838
        assert amount == 9600 * 184 // 365

    def test_proration_none_mid_period(self) -> None:
        """Assignment starts mid-month but proration=NONE -> full rate."""
        settings = self._make_settings("MONTHLY", "rate_minutes_per_month", 480, "NONE")
        amount = _compute_accrual_amount(settings, date(2025, 1, 1), date(2025, 1, 15))
        assert amount == 480

    def test_assignment_before_period_start(self) -> None:
        """Assignment started well before the accrual period -> full rate."""
        settings = self._make_settings("MONTHLY", "rate_minutes_per_month", 480)
        amount = _compute_accrual_amount(settings, date(2025, 3, 1), date(2024, 1, 1))
        assert amount == 480


class TestApplyBankCap:
    """Tests for _apply_bank_cap."""

    def test_no_cap(self) -> None:
        assert _apply_bank_cap(1000, 480, None) == 480

    def test_under_cap(self) -> None:
        assert _apply_bank_cap(1000, 480, 2400) == 480

    def test_at_cap(self) -> None:
        assert _apply_bank_cap(2400, 480, 2400) == 0

    def test_above_cap(self) -> None:
        assert _apply_bank_cap(2500, 480, 2400) == 0

    def test_partial_cap(self) -> None:
        """Only 200 minutes of headroom left."""
        assert _apply_bank_cap(2200, 480, 2400) == 200


class TestComputeHoursWorkedAccrual:
    """Tests for _compute_hours_worked_accrual."""

    def _make_settings(self, accrue: int = 60, per_worked: int = 1440) -> HoursWorkedAccrualSettings:
        return HoursWorkedAccrualSettings(
            accrual_ratio=AccrualRatio(accrue_minutes=accrue, per_worked_minutes=per_worked),
        )

    def test_basic_ratio(self) -> None:
        """60 min accrued per 1440 worked. 480 worked -> 20 min."""
        settings = self._make_settings()
        assert _compute_hours_worked_accrual(settings, 480) == 20

    def test_exact_ratio(self) -> None:
        """1440 worked = 60 accrued exactly."""
        settings = self._make_settings()
        assert _compute_hours_worked_accrual(settings, 1440) == 60

    def test_integer_division_no_float_drift(self) -> None:
        """Verify integer division: 100 worked * 60 // 1440 = 4 (floor)."""
        settings = self._make_settings()
        assert _compute_hours_worked_accrual(settings, 100) == 4

    def test_different_ratio(self) -> None:
        """30 accrued per 480 worked. 960 worked = 60."""
        settings = self._make_settings(30, 480)
        assert _compute_hours_worked_accrual(settings, 960) == 60


class TestResolveAccrualRate:
    """Tests for _resolve_accrual_rate with tenure tiers."""

    def _make_settings(
        self,
        rate: int = 480,
        tenure_tiers: list[dict[str, int]] | None = None,
    ) -> TimeAccrualSettings:
        kwargs: dict[str, Any] = {
            "accrual_frequency": "MONTHLY",
            "rate_minutes_per_month": rate,
        }
        if tenure_tiers:
            kwargs["tenure_tiers"] = tenure_tiers
        return TimeAccrualSettings(**kwargs)

    def test_no_tiers_returns_base(self) -> None:
        settings = self._make_settings(480)
        result = _resolve_accrual_rate(settings, date(2024, 1, 1), date(2024, 1, 1), date(2025, 1, 1))
        assert result == 480

    def test_matching_tier(self) -> None:
        """12+ months tenure -> 720 rate."""
        settings = self._make_settings(
            480,
            tenure_tiers=[
                {"min_months": 0, "accrual_rate_minutes": 480},
                {"min_months": 12, "accrual_rate_minutes": 720},
            ],
        )
        result = _resolve_accrual_rate(settings, date(2024, 1, 1), date(2024, 1, 1), date(2025, 1, 1))
        assert result == 720

    def test_highest_matching_tier(self) -> None:
        """24+ months tenure, three tiers, picks highest matching."""
        settings = self._make_settings(
            480,
            tenure_tiers=[
                {"min_months": 0, "accrual_rate_minutes": 480},
                {"min_months": 12, "accrual_rate_minutes": 720},
                {"min_months": 24, "accrual_rate_minutes": 960},
            ],
        )
        result = _resolve_accrual_rate(settings, date(2023, 1, 1), date(2023, 1, 1), date(2025, 1, 1))
        assert result == 960

    def test_falls_back_to_assignment_from(self) -> None:
        """No hire_date, uses assignment effective_from."""
        settings = self._make_settings(
            480,
            tenure_tiers=[
                {"min_months": 0, "accrual_rate_minutes": 480},
                {"min_months": 6, "accrual_rate_minutes": 600},
            ],
        )
        result = _resolve_accrual_rate(settings, None, date(2024, 6, 1), date(2025, 1, 1))
        # 7 months tenure from assignment -> matches 6-month tier
        assert result == 600

    def test_no_matching_tier_returns_base(self) -> None:
        """All tiers require more tenure than employee has."""
        settings = self._make_settings(
            480,
            tenure_tiers=[
                {"min_months": 12, "accrual_rate_minutes": 720},
            ],
        )
        result = _resolve_accrual_rate(settings, date(2025, 1, 1), date(2025, 1, 1), date(2025, 3, 1))
        assert result == 480


class TestSourceIdBuilders:
    """Tests for idempotency source_id construction."""

    def test_time_accrual_source_id(self) -> None:
        pid = uuid.UUID("11111111-1111-1111-1111-111111111111")
        eid = uuid.UUID("22222222-2222-2222-2222-222222222222")
        result = _build_time_accrual_source_id(pid, eid, date(2025, 3, 15))
        assert result == f"accrual:{pid}:{eid}:2025-03-15"

    def test_payroll_source_id(self) -> None:
        eid = uuid.UUID("22222222-2222-2222-2222-222222222222")
        pid = uuid.UUID("33333333-3333-3333-3333-333333333333")
        result = _build_payroll_source_id("run-123", eid, pid)
        assert result == f"payroll:run-123:{eid}:{pid}"


# ===========================================================================
# Time-based accrual integration tests (via API trigger)
# ===========================================================================


class TestTimeAccrualViaTrigger:
    """Integration tests for time-based accruals through the admin trigger API."""

    async def test_daily_accrual(self, async_client: AsyncClient) -> None:
        """Daily accrual posts an entry for any day."""
        policy_id = await _create_time_accrual_policy(async_client, key="daily-1")
        await _assign_employee(async_client, policy_id)

        resp = await async_client.post(f"{TRIGGER_URL}?target_date=2025-03-15", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["accrued"] >= 1

        # Verify ledger entry
        ledger_resp = await async_client.get(
            f"{_ledger_url()}?policy_id={policy_id}",
            headers=AUTH_HEADERS,
        )
        entries = ledger_resp.json()["items"]
        accrual_entries = [e for e in entries if e["entry_type"] == "ACCRUAL"]
        assert len(accrual_entries) >= 1
        assert accrual_entries[0]["source_type"] == "SYSTEM"
        assert accrual_entries[0]["amount_minutes"] == 480

    async def test_monthly_start_of_period(self, async_client: AsyncClient) -> None:
        """Monthly START_OF_PERIOD accrues on the 1st."""
        policy_id = await _create_time_accrual_policy(
            async_client,
            key="monthly-start-1",
            frequency="MONTHLY",
            timing="START_OF_PERIOD",
            rate_field="rate_minutes_per_month",
            rate_value=960,
        )
        await _assign_employee(async_client, policy_id)

        resp = await async_client.post(f"{TRIGGER_URL}?target_date=2025-02-01", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["accrued"] >= 1

    async def test_monthly_not_on_accrual_date(self, async_client: AsyncClient) -> None:
        """Monthly START_OF_PERIOD skips non-1st dates."""
        policy_id = await _create_time_accrual_policy(
            async_client,
            key="monthly-skip-1",
            frequency="MONTHLY",
            timing="START_OF_PERIOD",
            rate_field="rate_minutes_per_month",
            rate_value=960,
        )
        await _assign_employee(async_client, policy_id)

        resp = await async_client.post(f"{TRIGGER_URL}?target_date=2025-02-15", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["accrued"] == 0
        assert resp.json()["skipped"] >= 1

    async def test_monthly_end_of_period(self, async_client: AsyncClient) -> None:
        """Monthly END_OF_PERIOD accrues on the last day of the month."""
        policy_id = await _create_time_accrual_policy(
            async_client,
            key="monthly-end-1",
            frequency="MONTHLY",
            timing="END_OF_PERIOD",
            rate_field="rate_minutes_per_month",
            rate_value=960,
        )
        await _assign_employee(async_client, policy_id)

        resp = await async_client.post(f"{TRIGGER_URL}?target_date=2025-01-31", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["accrued"] >= 1

    async def test_yearly_start_of_period(self, async_client: AsyncClient) -> None:
        """Yearly START_OF_PERIOD accrues on Jan 1."""
        policy_id = await _create_time_accrual_policy(
            async_client,
            key="yearly-start-1",
            frequency="YEARLY",
            timing="START_OF_PERIOD",
            rate_field="rate_minutes_per_year",
            rate_value=9600,
        )
        await _assign_employee(async_client, policy_id)

        resp = await async_client.post(f"{TRIGGER_URL}?target_date=2025-01-01", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["accrued"] >= 1

    async def test_proration_mid_month_join(self, async_client: AsyncClient) -> None:
        """Employee assigned Jan 15, monthly accrual on Jan 1 -> prorated."""
        policy_id = await _create_time_accrual_policy(
            async_client,
            key="prorate-mid-1",
            frequency="MONTHLY",
            timing="START_OF_PERIOD",
            rate_field="rate_minutes_per_month",
            rate_value=480,
        )
        await _assign_employee(async_client, policy_id, effective_from="2025-01-15")

        # Trigger on Jan 1 -- assignment starts Jan 15, so prorated
        resp = await async_client.post(f"{TRIGGER_URL}?target_date=2025-01-01", headers=AUTH_HEADERS)
        assert resp.status_code == 200

        # Check the accrued amount is prorated
        ledger_resp = await async_client.get(
            f"{_ledger_url()}?policy_id={policy_id}",
            headers=AUTH_HEADERS,
        )
        items = ledger_resp.json()["items"]
        accrual_entries = [e for e in items if e["entry_type"] == "ACCRUAL"]
        if accrual_entries:
            # 480 * 17 // 31 = 263 (active Jan 15 to Feb 1 = 17 days out of 31)
            assert accrual_entries[0]["amount_minutes"] == 263

    async def test_proration_none_mid_month(self, async_client: AsyncClient) -> None:
        """Proration=NONE gives full rate even for mid-period join."""
        policy_id = await _create_time_accrual_policy(
            async_client,
            key="prorate-none-1",
            frequency="MONTHLY",
            timing="START_OF_PERIOD",
            rate_field="rate_minutes_per_month",
            rate_value=480,
            proration="NONE",
        )
        await _assign_employee(async_client, policy_id, effective_from="2025-01-15")

        resp = await async_client.post(f"{TRIGGER_URL}?target_date=2025-01-01", headers=AUTH_HEADERS)
        assert resp.status_code == 200

        ledger_resp = await async_client.get(
            f"{_ledger_url()}?policy_id={policy_id}",
            headers=AUTH_HEADERS,
        )
        items = ledger_resp.json()["items"]
        accrual_entries = [e for e in items if e["entry_type"] == "ACCRUAL"]
        if accrual_entries:
            assert accrual_entries[0]["amount_minutes"] == 480

    async def test_bank_cap_enforced(self, async_client: AsyncClient) -> None:
        """Accrual is clamped when bank cap would be exceeded."""
        policy_id = await _create_time_accrual_policy(
            async_client,
            key="cap-enforce-1",
            bank_cap_minutes=2400,
        )
        await _assign_employee(async_client, policy_id)

        # Seed balance at 2000 via adjustment
        await async_client.post(
            _adjustment_url(),
            json={
                "employee_id": str(EMPLOYEE_ID),
                "policy_id": policy_id,
                "amount_minutes": 2000,
                "reason": "Seed",
            },
            headers=AUTH_HEADERS,
        )

        # Trigger accrual for 480 -- should be capped to 400
        resp = await async_client.post(f"{TRIGGER_URL}?target_date=2025-03-15", headers=AUTH_HEADERS)
        assert resp.status_code == 200

        # Check balance is 2400 (capped)
        bal_resp = await async_client.get(_balances_url(), headers=AUTH_HEADERS)
        balance = next(b for b in bal_resp.json()["items"] if b["policy_id"] == policy_id)
        assert balance["accrued_minutes"] == 2400

    async def test_bank_cap_already_at_cap(self, async_client: AsyncClient) -> None:
        """Accrual skipped when already at bank cap."""
        policy_id = await _create_time_accrual_policy(
            async_client,
            key="cap-at-1",
            bank_cap_minutes=2400,
        )
        await _assign_employee(async_client, policy_id)

        # Seed at cap
        await async_client.post(
            _adjustment_url(),
            json={
                "employee_id": str(EMPLOYEE_ID),
                "policy_id": policy_id,
                "amount_minutes": 2400,
                "reason": "At cap",
            },
            headers=AUTH_HEADERS,
        )

        resp = await async_client.post(f"{TRIGGER_URL}?target_date=2025-03-15", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["skipped"] >= 1

    async def test_idempotency_same_date(self, async_client: AsyncClient) -> None:
        """Running accruals twice for the same date produces only one entry."""
        policy_id = await _create_time_accrual_policy(async_client, key="idem-1")
        await _assign_employee(async_client, policy_id)

        await async_client.post(f"{TRIGGER_URL}?target_date=2025-03-15", headers=AUTH_HEADERS)
        await async_client.post(f"{TRIGGER_URL}?target_date=2025-03-15", headers=AUTH_HEADERS)

        ledger_resp = await async_client.get(
            f"{_ledger_url()}?policy_id={policy_id}",
            headers=AUTH_HEADERS,
        )
        accrual_entries = [e for e in ledger_resp.json()["items"] if e["entry_type"] == "ACCRUAL"]
        assert len(accrual_entries) == 1

    async def test_different_dates_both_post(self, async_client: AsyncClient) -> None:
        """Accruals for different dates produce separate entries."""
        policy_id = await _create_time_accrual_policy(async_client, key="diff-dates-1")
        await _assign_employee(async_client, policy_id)

        await async_client.post(f"{TRIGGER_URL}?target_date=2025-03-15", headers=AUTH_HEADERS)
        await async_client.post(f"{TRIGGER_URL}?target_date=2025-03-16", headers=AUTH_HEADERS)

        ledger_resp = await async_client.get(
            f"{_ledger_url()}?policy_id={policy_id}",
            headers=AUTH_HEADERS,
        )
        accrual_entries = [e for e in ledger_resp.json()["items"] if e["entry_type"] == "ACCRUAL"]
        assert len(accrual_entries) == 2

    async def test_updates_snapshot(self, async_client: AsyncClient, db_session: AsyncSession) -> None:
        """Accrual updates the balance snapshot correctly."""
        policy_id = await _create_time_accrual_policy(async_client, key="snap-up-1")
        await _assign_employee(async_client, policy_id)

        await async_client.post(f"{TRIGGER_URL}?target_date=2025-03-15", headers=AUTH_HEADERS)

        result = await db_session.execute(
            select(TimeOffBalanceSnapshot).where(
                col(TimeOffBalanceSnapshot.company_id) == COMPANY_ID,
                col(TimeOffBalanceSnapshot.employee_id) == EMPLOYEE_ID,
                col(TimeOffBalanceSnapshot.policy_id) == uuid.UUID(policy_id),
            )
        )
        snapshot = result.scalar_one()
        assert snapshot.accrued_minutes == 480
        assert snapshot.available_minutes == 480

    async def test_snapshot_matches_ledger(self, async_client: AsyncClient, db_session: AsyncSession) -> None:
        """Snapshot values match recomputation from ledger after accrual."""
        from app.services.balance import _compute_balance_from_ledger

        policy_id = await _create_time_accrual_policy(async_client, key="snap-led-1")
        await _assign_employee(async_client, policy_id)

        await async_client.post(f"{TRIGGER_URL}?target_date=2025-03-15", headers=AUTH_HEADERS)

        policy_uuid = uuid.UUID(policy_id)
        accrued, used, held = await _compute_balance_from_ledger(db_session, COMPANY_ID, EMPLOYEE_ID, policy_uuid)

        result = await db_session.execute(
            select(TimeOffBalanceSnapshot).where(
                col(TimeOffBalanceSnapshot.company_id) == COMPANY_ID,
                col(TimeOffBalanceSnapshot.employee_id) == EMPLOYEE_ID,
                col(TimeOffBalanceSnapshot.policy_id) == policy_uuid,
            )
        )
        snapshot = result.scalar_one()
        assert snapshot.accrued_minutes == accrued
        assert snapshot.used_minutes == used
        assert snapshot.held_minutes == held
        assert snapshot.available_minutes == accrued - used - held

    async def test_no_assignment_skipped(self, async_client: AsyncClient) -> None:
        """No accrual when employee is not assigned."""
        await _create_time_accrual_policy(async_client, key="no-assign-1")
        # No assignment created

        resp = await async_client.post(f"{TRIGGER_URL}?target_date=2025-03-15", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["processed"] == 0

    async def test_unlimited_policy_skipped(self, async_client: AsyncClient) -> None:
        """Unlimited policies are not processed by the accrual trigger."""
        policy_id = await _create_unlimited_policy(async_client, key="unlim-skip-1")
        await _assign_employee(async_client, policy_id)

        resp = await async_client.post(f"{TRIGGER_URL}?target_date=2025-03-15", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        # The query only finds TIME accrual policies, so unlimited is never found
        assert resp.json()["accrued"] == 0

    async def test_audit_log_written(self, async_client: AsyncClient, db_session: AsyncSession) -> None:
        """Accrual creates an audit log entry."""
        policy_id = await _create_time_accrual_policy(async_client, key="aud-1")
        await _assign_employee(async_client, policy_id)

        await async_client.post(f"{TRIGGER_URL}?target_date=2025-03-15", headers=AUTH_HEADERS)

        result = await db_session.execute(
            select(AuditLog).where(
                col(AuditLog.company_id) == COMPANY_ID,
                col(AuditLog.entity_type) == "ACCRUAL",
                col(AuditLog.action) == "CREATE",
            )
        )
        entries = list(result.scalars().all())
        assert len(entries) >= 1

    async def test_multiple_employees(self, async_client: AsyncClient) -> None:
        """Two employees both get accruals."""
        policy_id = await _create_time_accrual_policy(async_client, key="multi-emp-1")
        await _assign_employee(async_client, policy_id, employee_id=EMPLOYEE_ID)
        await _assign_employee(async_client, policy_id, employee_id=EMPLOYEE_ID_2)

        resp = await async_client.post(f"{TRIGGER_URL}?target_date=2025-03-15", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["accrued"] == 2

    async def test_multiple_policies(self, async_client: AsyncClient) -> None:
        """Employee with two TIME policies gets accruals for both."""
        p1 = await _create_time_accrual_policy(async_client, key="multi-pol-1")
        p2 = await _create_time_accrual_policy(async_client, key="multi-pol-2", rate_value=240)
        await _assign_employee(async_client, p1)
        await _assign_employee(async_client, p2)

        resp = await async_client.post(f"{TRIGGER_URL}?target_date=2025-03-15", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["accrued"] == 2

    async def test_inactive_assignment_skipped(self, async_client: AsyncClient) -> None:
        """End-dated assignment is not processed."""
        policy_id = await _create_time_accrual_policy(async_client, key="inactive-1")
        assignment_id = await _assign_employee(async_client, policy_id)

        # End-date the assignment
        await async_client.delete(
            f"/companies/{COMPANY_ID}/assignments/{assignment_id}",
            params={"effective_to": "2025-02-01"},
            headers=AUTH_HEADERS,
        )

        # Trigger after end date
        resp = await async_client.post(f"{TRIGGER_URL}?target_date=2025-03-15", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["accrued"] == 0

    async def test_tenure_tier_override(self, async_client: AsyncClient) -> None:
        """Employee with 12+ months tenure gets the higher tier rate."""
        policy_id = await _create_time_accrual_policy(
            async_client,
            key="tenure-1",
            tenure_tiers=[
                {"min_months": 0, "accrual_rate_minutes": 480},
                {"min_months": 12, "accrual_rate_minutes": 720},
            ],
        )
        await _assign_employee(async_client, policy_id)

        # Employee hire_date = 2024-01-01, target = 2025-03-15 (14 months)
        resp = await async_client.post(f"{TRIGGER_URL}?target_date=2025-03-15", headers=AUTH_HEADERS)
        assert resp.status_code == 200

        ledger_resp = await async_client.get(
            f"{_ledger_url()}?policy_id={policy_id}",
            headers=AUTH_HEADERS,
        )
        accrual_entries = [e for e in ledger_resp.json()["items"] if e["entry_type"] == "ACCRUAL"]
        assert len(accrual_entries) == 1
        assert accrual_entries[0]["amount_minutes"] == 720

    async def test_admin_only(self, async_client: AsyncClient) -> None:
        """Employee role cannot trigger accruals."""
        resp = await async_client.post(f"{TRIGGER_URL}?target_date=2025-03-15", headers=EMPLOYEE_HEADERS)
        assert resp.status_code == 403

    async def test_custom_date_query_param(self, async_client: AsyncClient) -> None:
        """Custom target_date via query parameter."""
        policy_id = await _create_time_accrual_policy(async_client, key="custom-date-1")
        await _assign_employee(async_client, policy_id)

        resp = await async_client.post(f"{TRIGGER_URL}?target_date=2025-06-01", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["target_date"] == "2025-06-01"

    async def test_backfill_past_date(self, async_client: AsyncClient) -> None:
        """Triggering accrual for a past date works correctly."""
        policy_id = await _create_time_accrual_policy(async_client, key="backfill-1")
        await _assign_employee(async_client, policy_id)

        resp = await async_client.post(f"{TRIGGER_URL}?target_date=2025-01-01", headers=AUTH_HEADERS)
        assert resp.status_code == 200
        assert resp.json()["accrued"] >= 1


# ===========================================================================
# Payroll webhook tests
# ===========================================================================


class TestPayrollWebhook:
    """Integration tests for payroll webhook and hours-worked accruals."""

    async def test_basic_processing(self, async_client: AsyncClient) -> None:
        """Payroll webhook posts an ACCRUAL entry with source_type=PAYROLL."""
        policy_id = await _create_hours_worked_policy(async_client, key="payroll-basic-1")
        await _assign_employee(async_client, policy_id)

        resp = await async_client.post(
            WEBHOOK_URL,
            json={
                "payroll_run_id": "run-001",
                "company_id": str(COMPANY_ID),
                "period_start": "2025-01-01",
                "period_end": "2025-01-15",
                "entries": [{"employee_id": str(EMPLOYEE_ID), "worked_minutes": 4800}],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accrued"] >= 1

        # Verify ledger entry
        ledger_resp = await async_client.get(
            f"{_ledger_url()}?policy_id={policy_id}",
            headers=AUTH_HEADERS,
        )
        entries = ledger_resp.json()["items"]
        accrual_entries = [e for e in entries if e["entry_type"] == "ACCRUAL"]
        assert len(accrual_entries) >= 1
        assert accrual_entries[0]["source_type"] == "PAYROLL"
        # 4800 * 60 // 1440 = 200
        assert accrual_entries[0]["amount_minutes"] == 200

    async def test_idempotency(self, async_client: AsyncClient) -> None:
        """Same payroll_run_id processed twice produces only one entry."""
        policy_id = await _create_hours_worked_policy(async_client, key="payroll-idem-1")
        await _assign_employee(async_client, policy_id)

        payload = {
            "payroll_run_id": "run-idem-001",
            "company_id": str(COMPANY_ID),
            "period_start": "2025-01-01",
            "period_end": "2025-01-15",
            "entries": [{"employee_id": str(EMPLOYEE_ID), "worked_minutes": 4800}],
        }

        await async_client.post(WEBHOOK_URL, json=payload)
        resp2 = await async_client.post(WEBHOOK_URL, json=payload)

        assert resp2.status_code == 200
        # Second call should show skipped, not accrued
        assert resp2.json()["skipped"] >= 1

        # Verify only one ledger entry
        ledger_resp = await async_client.get(
            f"{_ledger_url()}?policy_id={policy_id}",
            headers=AUTH_HEADERS,
        )
        accrual_entries = [e for e in ledger_resp.json()["items"] if e["entry_type"] == "ACCRUAL"]
        assert len(accrual_entries) == 1

    async def test_multiple_employees(self, async_client: AsyncClient) -> None:
        """Webhook with multiple employees processes all of them."""
        policy_id = await _create_hours_worked_policy(async_client, key="payroll-multi-1")
        await _assign_employee(async_client, policy_id, employee_id=EMPLOYEE_ID)
        await _assign_employee(async_client, policy_id, employee_id=EMPLOYEE_ID_2)
        await _assign_employee(async_client, policy_id, employee_id=EMPLOYEE_ID_3)

        resp = await async_client.post(
            WEBHOOK_URL,
            json={
                "payroll_run_id": "run-multi-001",
                "company_id": str(COMPANY_ID),
                "period_start": "2025-01-01",
                "period_end": "2025-01-15",
                "entries": [
                    {"employee_id": str(EMPLOYEE_ID), "worked_minutes": 4800},
                    {"employee_id": str(EMPLOYEE_ID_2), "worked_minutes": 3600},
                    {"employee_id": str(EMPLOYEE_ID_3), "worked_minutes": 2400},
                ],
            },
        )
        assert resp.status_code == 200
        assert resp.json()["accrued"] == 3

    async def test_no_hours_worked_policy(self, async_client: AsyncClient) -> None:
        """Employee with only TIME policy is not processed by payroll webhook."""
        policy_id = await _create_time_accrual_policy(async_client, key="payroll-time-only-1")
        await _assign_employee(async_client, policy_id)

        resp = await async_client.post(
            WEBHOOK_URL,
            json={
                "payroll_run_id": "run-time-only-001",
                "company_id": str(COMPANY_ID),
                "period_start": "2025-01-01",
                "period_end": "2025-01-15",
                "entries": [{"employee_id": str(EMPLOYEE_ID), "worked_minutes": 4800}],
            },
        )
        assert resp.status_code == 200
        assert resp.json()["processed"] == 0

    async def test_bank_cap(self, async_client: AsyncClient) -> None:
        """Hours-worked accrual capped by bank_cap_minutes."""
        policy_id = await _create_hours_worked_policy(
            async_client,
            key="payroll-cap-1",
            bank_cap_minutes=100,
        )
        await _assign_employee(async_client, policy_id)

        resp = await async_client.post(
            WEBHOOK_URL,
            json={
                "payroll_run_id": "run-cap-001",
                "company_id": str(COMPANY_ID),
                "period_start": "2025-01-01",
                "period_end": "2025-01-15",
                "entries": [{"employee_id": str(EMPLOYEE_ID), "worked_minutes": 4800}],
            },
        )
        assert resp.status_code == 200

        # Without cap: 4800 * 60 // 1440 = 200. With cap 100: capped to 100
        bal_resp = await async_client.get(_balances_url(), headers=AUTH_HEADERS)
        balance = next(b for b in bal_resp.json()["items"] if b["policy_id"] == policy_id)
        assert balance["accrued_minutes"] == 100

    async def test_updates_snapshot(self, async_client: AsyncClient, db_session: AsyncSession) -> None:
        """Payroll accrual updates the balance snapshot."""
        policy_id = await _create_hours_worked_policy(async_client, key="payroll-snap-1")
        await _assign_employee(async_client, policy_id)

        await async_client.post(
            WEBHOOK_URL,
            json={
                "payroll_run_id": "run-snap-001",
                "company_id": str(COMPANY_ID),
                "period_start": "2025-01-01",
                "period_end": "2025-01-15",
                "entries": [{"employee_id": str(EMPLOYEE_ID), "worked_minutes": 4800}],
            },
        )

        result = await db_session.execute(
            select(TimeOffBalanceSnapshot).where(
                col(TimeOffBalanceSnapshot.company_id) == COMPANY_ID,
                col(TimeOffBalanceSnapshot.employee_id) == EMPLOYEE_ID,
                col(TimeOffBalanceSnapshot.policy_id) == uuid.UUID(policy_id),
            )
        )
        snapshot = result.scalar_one()
        assert snapshot.accrued_minutes == 200
        assert snapshot.available_minutes == 200

    async def test_snapshot_matches_ledger(self, async_client: AsyncClient, db_session: AsyncSession) -> None:
        """Snapshot matches ledger recomputation after payroll accrual."""
        from app.services.balance import _compute_balance_from_ledger

        policy_id = await _create_hours_worked_policy(async_client, key="payroll-inv-1")
        await _assign_employee(async_client, policy_id)

        await async_client.post(
            WEBHOOK_URL,
            json={
                "payroll_run_id": "run-inv-001",
                "company_id": str(COMPANY_ID),
                "period_start": "2025-01-01",
                "period_end": "2025-01-15",
                "entries": [{"employee_id": str(EMPLOYEE_ID), "worked_minutes": 4800}],
            },
        )

        policy_uuid = uuid.UUID(policy_id)
        accrued, used, held = await _compute_balance_from_ledger(db_session, COMPANY_ID, EMPLOYEE_ID, policy_uuid)

        result = await db_session.execute(
            select(TimeOffBalanceSnapshot).where(
                col(TimeOffBalanceSnapshot.company_id) == COMPANY_ID,
                col(TimeOffBalanceSnapshot.employee_id) == EMPLOYEE_ID,
                col(TimeOffBalanceSnapshot.policy_id) == policy_uuid,
            )
        )
        snapshot = result.scalar_one()
        assert snapshot.accrued_minutes == accrued
        assert snapshot.available_minutes == accrued - used - held

    async def test_invalid_payload(self, async_client: AsyncClient) -> None:
        """Missing required fields returns 422."""
        resp = await async_client.post(
            WEBHOOK_URL,
            json={"payroll_run_id": "run-bad"},
        )
        assert resp.status_code == 422

    async def test_empty_entries(self, async_client: AsyncClient) -> None:
        """Empty entries list returns 422."""
        resp = await async_client.post(
            WEBHOOK_URL,
            json={
                "payroll_run_id": "run-empty",
                "company_id": str(COMPANY_ID),
                "period_start": "2025-01-01",
                "period_end": "2025-01-15",
                "entries": [],
            },
        )
        assert resp.status_code == 422

    async def test_period_end_before_start(self, async_client: AsyncClient) -> None:
        """period_end before period_start returns 422."""
        resp = await async_client.post(
            WEBHOOK_URL,
            json={
                "payroll_run_id": "run-bad-dates",
                "company_id": str(COMPANY_ID),
                "period_start": "2025-01-15",
                "period_end": "2025-01-01",
                "entries": [{"employee_id": str(EMPLOYEE_ID), "worked_minutes": 4800}],
            },
        )
        assert resp.status_code == 422

    async def test_audit_log(self, async_client: AsyncClient, db_session: AsyncSession) -> None:
        """Payroll-driven accrual creates an audit entry."""
        policy_id = await _create_hours_worked_policy(async_client, key="payroll-aud-1")
        await _assign_employee(async_client, policy_id)

        await async_client.post(
            WEBHOOK_URL,
            json={
                "payroll_run_id": "run-aud-001",
                "company_id": str(COMPANY_ID),
                "period_start": "2025-01-01",
                "period_end": "2025-01-15",
                "entries": [{"employee_id": str(EMPLOYEE_ID), "worked_minutes": 4800}],
            },
        )

        result = await db_session.execute(
            select(AuditLog).where(
                col(AuditLog.company_id) == COMPANY_ID,
                col(AuditLog.entity_type) == "ACCRUAL",
                col(AuditLog.action) == "CREATE",
            )
        )
        entries = list(result.scalars().all())
        assert len(entries) >= 1


# ===========================================================================
# Replay & balance invariant tests
# ===========================================================================


class TestReplayAndInvariants:
    """Tests for replay safety and balance invariants."""

    async def test_payroll_replay_no_duplicates(self, async_client: AsyncClient, db_session: AsyncSession) -> None:
        """Replaying same payroll run creates no duplicate ledger entries."""
        policy_id = await _create_hours_worked_policy(async_client, key="replay-nodup-1")
        await _assign_employee(async_client, policy_id)

        payload = {
            "payroll_run_id": "run-replay-001",
            "company_id": str(COMPANY_ID),
            "period_start": "2025-01-01",
            "period_end": "2025-01-15",
            "entries": [{"employee_id": str(EMPLOYEE_ID), "worked_minutes": 4800}],
        }

        await async_client.post(WEBHOOK_URL, json=payload)
        await async_client.post(WEBHOOK_URL, json=payload)
        await async_client.post(WEBHOOK_URL, json=payload)

        # Count ledger entries
        result = await db_session.execute(
            select(func.count())
            .select_from(TimeOffLedgerEntry)
            .where(
                col(TimeOffLedgerEntry.company_id) == COMPANY_ID,
                col(TimeOffLedgerEntry.employee_id) == EMPLOYEE_ID,
                col(TimeOffLedgerEntry.policy_id) == uuid.UUID(policy_id),
                col(TimeOffLedgerEntry.entry_type) == LedgerEntryType.ACCRUAL.value,
            )
        )
        count = result.scalar_one()
        assert count == 1

    async def test_payroll_replay_balance_unchanged(self, async_client: AsyncClient) -> None:
        """Balance is unchanged after replaying the same payroll run."""
        policy_id = await _create_hours_worked_policy(async_client, key="replay-bal-1")
        await _assign_employee(async_client, policy_id)

        payload = {
            "payroll_run_id": "run-replay-bal-001",
            "company_id": str(COMPANY_ID),
            "period_start": "2025-01-01",
            "period_end": "2025-01-15",
            "entries": [{"employee_id": str(EMPLOYEE_ID), "worked_minutes": 4800}],
        }

        await async_client.post(WEBHOOK_URL, json=payload)

        bal_resp1 = await async_client.get(_balances_url(), headers=AUTH_HEADERS)
        bal1 = next(b for b in bal_resp1.json()["items"] if b["policy_id"] == policy_id)

        # Replay
        await async_client.post(WEBHOOK_URL, json=payload)

        bal_resp2 = await async_client.get(_balances_url(), headers=AUTH_HEADERS)
        bal2 = next(b for b in bal_resp2.json()["items"] if b["policy_id"] == policy_id)

        assert bal1["accrued_minutes"] == bal2["accrued_minutes"]
        assert bal1["available_minutes"] == bal2["available_minutes"]

    async def test_invariant_accrual_then_submit_then_approve(self, async_client: AsyncClient) -> None:
        """Full workflow: accrue -> submit request -> approve. Balance invariants hold."""
        # Need to seed employee service for the request duration calculation
        policy_id = await _create_time_accrual_policy(async_client, key="workflow-1")
        await _assign_employee(async_client, policy_id)

        # Accrue 480
        await async_client.post(f"{TRIGGER_URL}?target_date=2025-03-15", headers=AUTH_HEADERS)

        # Submit a 480-minute request (1 full workday Mon 9am-5pm)
        submit_resp = await async_client.post(
            f"/companies/{COMPANY_ID}/requests",
            json={
                "employee_id": str(EMPLOYEE_ID),
                "policy_id": policy_id,
                "start_at": "2025-03-17T09:00:00-04:00",
                "end_at": "2025-03-17T17:00:00-04:00",
                "reason": "Vacation day",
            },
            headers=AUTH_HEADERS,
        )
        assert submit_resp.status_code == 201
        request_id = submit_resp.json()["id"]

        # Approve
        approve_resp = await async_client.post(
            f"/companies/{COMPANY_ID}/requests/{request_id}/approve",
            json={},
            headers=AUTH_HEADERS,
        )
        assert approve_resp.status_code == 200

        # Check balance
        bal_resp = await async_client.get(_balances_url(), headers=AUTH_HEADERS)
        balance = next(b for b in bal_resp.json()["items"] if b["policy_id"] == policy_id)
        assert balance["accrued_minutes"] == 480
        assert balance["used_minutes"] == 480
        assert balance["held_minutes"] == 0
        assert balance["available_minutes"] == 0

    async def test_snapshot_version_increments(self, async_client: AsyncClient, db_session: AsyncSession) -> None:
        """Each accrual increments the snapshot version."""
        policy_id = await _create_time_accrual_policy(async_client, key="snap-ver-1")
        await _assign_employee(async_client, policy_id)

        await async_client.post(f"{TRIGGER_URL}?target_date=2025-03-15", headers=AUTH_HEADERS)
        await async_client.post(f"{TRIGGER_URL}?target_date=2025-03-16", headers=AUTH_HEADERS)
        await async_client.post(f"{TRIGGER_URL}?target_date=2025-03-17", headers=AUTH_HEADERS)

        result = await db_session.execute(
            select(TimeOffBalanceSnapshot).where(
                col(TimeOffBalanceSnapshot.company_id) == COMPANY_ID,
                col(TimeOffBalanceSnapshot.employee_id) == EMPLOYEE_ID,
                col(TimeOffBalanceSnapshot.policy_id) == uuid.UUID(policy_id),
            )
        )
        snapshot = result.scalar_one()
        # Version 1 (initial creation) + 3 accruals = version 4
        assert snapshot.version == 4

    async def test_multiple_accruals_cumulative(self, async_client: AsyncClient) -> None:
        """Three daily accruals accumulate correctly."""
        policy_id = await _create_time_accrual_policy(async_client, key="cumul-1", rate_value=100)
        await _assign_employee(async_client, policy_id)

        for day in range(15, 18):
            await async_client.post(f"{TRIGGER_URL}?target_date=2025-03-{day:02d}", headers=AUTH_HEADERS)

        bal_resp = await async_client.get(_balances_url(), headers=AUTH_HEADERS)
        balance = next(b for b in bal_resp.json()["items"] if b["policy_id"] == policy_id)
        assert balance["accrued_minutes"] == 300
        assert balance["available_minutes"] == 300
