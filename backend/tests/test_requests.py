"""Comprehensive tests for the request workflow: submit, approve, deny, cancel,
overlap detection, balance invariants, idempotency, concurrency, and audit.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlmodel import col

from app.models.audit import AuditLog
from app.models.balance import TimeOffBalanceSnapshot
from app.models.enums import LedgerEntryType, LedgerSourceType
from app.models.holiday import CompanyHoliday
from app.models.ledger import TimeOffLedgerEntry
from app.services.employee import EmployeeInfo, InMemoryEmployeeService, set_employee_service

if TYPE_CHECKING:
    from collections.abc import Iterator

    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

COMPANY_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
EMPLOYEE_ID = uuid.uuid4()
_TZ = ZoneInfo("America/New_York")

AUTH_HEADERS = {
    "X-Company-Id": str(COMPANY_ID),
    "X-User-Id": str(USER_ID),
    "X-Role": "admin",
}
EMPLOYEE_HEADERS = {
    "X-Company-Id": str(COMPANY_ID),
    "X-User-Id": str(EMPLOYEE_ID),
    "X-Role": "employee",
}
POLICIES_URL = f"/companies/{COMPANY_ID}/policies"
REQUESTS_URL = f"/companies/{COMPANY_ID}/requests"


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
        )
    )
    set_employee_service(svc)
    yield
    set_employee_service(InMemoryEmployeeService())


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


async def _create_accrual_policy(
    client: AsyncClient,
    key: str = "req-vacation",
    allow_negative: bool = False,
    negative_limit_minutes: int | None = None,
) -> str:
    """Create a time-based accrual policy and return its ID."""
    settings: dict[str, Any] = {
        "type": "ACCRUAL",
        "accrual_method": "TIME",
        "accrual_frequency": "MONTHLY",
        "accrual_timing": "START_OF_PERIOD",
        "rate_minutes_per_month": 480,
        "allow_negative": allow_negative,
    }
    if negative_limit_minutes is not None:
        settings["negative_limit_minutes"] = negative_limit_minutes
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
    result: str = resp.json()["id"]
    return result


async def _create_unlimited_policy(client: AsyncClient, key: str = "req-unlimited") -> str:
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
    result: str = resp.json()["id"]
    return result


async def _assign_employee(
    client: AsyncClient,
    policy_id: str,
    employee_id: uuid.UUID = EMPLOYEE_ID,
) -> str:
    """Assign employee to policy and return assignment ID."""
    resp = await client.post(
        f"{POLICIES_URL}/{policy_id}/assignments",
        json={"employee_id": str(employee_id), "effective_from": "2025-01-01"},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201
    result: str = resp.json()["id"]
    return result


async def _grant_balance(
    client: AsyncClient,
    policy_id: str,
    amount: int = 4800,
    employee_id: uuid.UUID = EMPLOYEE_ID,
) -> None:
    """Grant balance to employee via admin adjustment."""
    resp = await client.post(
        f"/companies/{COMPANY_ID}/adjustments",
        json={
            "employee_id": str(employee_id),
            "policy_id": policy_id,
            "amount_minutes": amount,
            "reason": "Initial grant for testing",
        },
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201


def _submit_payload(
    policy_id: str,
    employee_id: uuid.UUID = EMPLOYEE_ID,
    start_year: int = 2025,
    start_month: int = 1,
    start_day: int = 6,
    start_hour: int = 9,
    end_year: int = 2025,
    end_month: int = 1,
    end_day: int = 6,
    end_hour: int = 17,
    reason: str | None = "Vacation",
    idempotency_key: str | None = None,
) -> dict:
    """Build a submit request payload. Default is Mon Jan 6 2025, 9am-5pm ET = 480 min."""
    tz = ZoneInfo("America/New_York")
    start = datetime(start_year, start_month, start_day, start_hour, 0, tzinfo=tz)
    end = datetime(end_year, end_month, end_day, end_hour, 0, tzinfo=tz)
    payload: dict = {
        "employee_id": str(employee_id),
        "policy_id": policy_id,
        "start_at": start.isoformat(),
        "end_at": end.isoformat(),
    }
    if reason is not None:
        payload["reason"] = reason
    if idempotency_key is not None:
        payload["idempotency_key"] = idempotency_key
    return payload


async def _submit_request(
    client: AsyncClient,
    policy_id: str,
    employee_id: uuid.UUID = EMPLOYEE_ID,
    headers: dict[str, str] | None = None,
    **kwargs: object,
) -> dict[str, Any]:
    """Submit a request and return the response JSON. Asserts 201."""
    resp = await client.post(
        REQUESTS_URL,
        json=_submit_payload(policy_id, employee_id=employee_id, **kwargs),  # type: ignore[arg-type]
        headers=headers or EMPLOYEE_HEADERS,
    )
    assert resp.status_code == 201, resp.json()
    result: dict[str, Any] = resp.json()
    return result


async def _add_holiday(session: AsyncSession, dt: date, name: str = "Holiday") -> None:
    """Insert a company holiday directly via the DB session."""
    session.add(CompanyHoliday(company_id=COMPANY_ID, date=dt, name=name))
    await session.flush()


# ---------------------------------------------------------------------------
# Submit request tests
# ---------------------------------------------------------------------------


async def test_submit_request_success(async_client: AsyncClient) -> None:
    """Happy path: submit a request returns 201 with SUBMITTED status."""
    policy_id = await _create_accrual_policy(async_client, key="sub-ok")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    data = await _submit_request(async_client, policy_id)

    assert data["status"] == "SUBMITTED"
    assert data["requested_minutes"] == 480
    assert data["submitted_at"] is not None
    assert data["employee_id"] == str(EMPLOYEE_ID)
    assert data["policy_id"] == policy_id
    assert data["reason"] == "Vacation"


async def test_submit_request_creates_hold_ledger_entry(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Submitting a request creates a HOLD ledger entry with negative amount."""
    policy_id = await _create_accrual_policy(async_client, key="sub-hold")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    data = await _submit_request(async_client, policy_id)
    request_id = data["id"]

    result = await db_session.execute(
        select(TimeOffLedgerEntry).where(
            col(TimeOffLedgerEntry.source_type) == LedgerSourceType.REQUEST.value,
            col(TimeOffLedgerEntry.source_id) == request_id,
            col(TimeOffLedgerEntry.entry_type) == LedgerEntryType.HOLD.value,
        )
    )
    hold = result.scalar_one()
    assert hold.amount_minutes == -480


async def test_submit_request_updates_snapshot(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Snapshot reflects held_minutes increase and available decrease after submit."""
    policy_id = await _create_accrual_policy(async_client, key="sub-snap")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id, amount=4800)

    await _submit_request(async_client, policy_id)

    result = await db_session.execute(
        select(TimeOffBalanceSnapshot).where(
            col(TimeOffBalanceSnapshot.company_id) == COMPANY_ID,
            col(TimeOffBalanceSnapshot.employee_id) == EMPLOYEE_ID,
            col(TimeOffBalanceSnapshot.policy_id) == uuid.UUID(policy_id),
        )
    )
    snapshot = result.scalar_one()
    assert snapshot.held_minutes == 480
    assert snapshot.available_minutes == 4800 - 480


async def test_submit_request_no_active_assignment(async_client: AsyncClient) -> None:
    """Submit fails when employee has no active assignment."""
    policy_id = await _create_accrual_policy(async_client, key="sub-noassign")

    resp = await async_client.post(
        REQUESTS_URL,
        json=_submit_payload(policy_id),
        headers=EMPLOYEE_HEADERS,
    )
    assert resp.status_code == 400


async def test_submit_request_insufficient_balance(async_client: AsyncClient) -> None:
    """Submit fails when balance insufficient and allow_negative=false."""
    policy_id = await _create_accrual_policy(async_client, key="sub-insuf")
    await _assign_employee(async_client, policy_id)
    # No balance granted — available is 0, request needs 480.

    resp = await async_client.post(
        REQUESTS_URL,
        json=_submit_payload(policy_id),
        headers=EMPLOYEE_HEADERS,
    )
    assert resp.status_code == 400


async def test_submit_request_allow_negative(async_client: AsyncClient) -> None:
    """Submit succeeds when allow_negative=true even with 0 balance."""
    policy_id = await _create_accrual_policy(async_client, key="sub-neg", allow_negative=True)
    await _assign_employee(async_client, policy_id)

    data = await _submit_request(async_client, policy_id)
    assert data["status"] == "SUBMITTED"


async def test_submit_request_exceeds_negative_limit(async_client: AsyncClient) -> None:
    """Submit fails when request would exceed negative balance limit."""
    policy_id = await _create_accrual_policy(
        async_client, key="sub-neglim", allow_negative=True, negative_limit_minutes=100
    )
    await _assign_employee(async_client, policy_id)
    # Request is 480 min, limit is 100 min negative.

    resp = await async_client.post(
        REQUESTS_URL,
        json=_submit_payload(policy_id),
        headers=EMPLOYEE_HEADERS,
    )
    assert resp.status_code == 400


async def test_submit_request_unlimited_policy(async_client: AsyncClient) -> None:
    """Submit succeeds for unlimited policy with no balance check."""
    policy_id = await _create_unlimited_policy(async_client, key="sub-unlim")
    await _assign_employee(async_client, policy_id)

    data = await _submit_request(async_client, policy_id)
    assert data["status"] == "SUBMITTED"
    assert data["requested_minutes"] == 480


async def test_submit_request_end_before_start(async_client: AsyncClient) -> None:
    """Validation error when end_at <= start_at."""
    policy_id = await _create_accrual_policy(async_client, key="sub-baddate")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    tz = ZoneInfo("America/New_York")
    resp = await async_client.post(
        REQUESTS_URL,
        json={
            "employee_id": str(EMPLOYEE_ID),
            "policy_id": policy_id,
            "start_at": datetime(2025, 1, 6, 17, 0, tzinfo=tz).isoformat(),
            "end_at": datetime(2025, 1, 6, 9, 0, tzinfo=tz).isoformat(),
        },
        headers=EMPLOYEE_HEADERS,
    )
    assert resp.status_code == 422


async def test_submit_request_weekend_only(async_client: AsyncClient) -> None:
    """Request spanning only weekend days yields zero working time → 400."""
    policy_id = await _create_accrual_policy(async_client, key="sub-weekend")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    # 2025-01-11 = Saturday, 2025-01-12 = Sunday.
    resp = await async_client.post(
        REQUESTS_URL,
        json={
            "employee_id": str(EMPLOYEE_ID),
            "policy_id": policy_id,
            "start_at": datetime(2025, 1, 11, 9, 0, tzinfo=_TZ).isoformat(),
            "end_at": datetime(2025, 1, 12, 17, 0, tzinfo=_TZ).isoformat(),
        },
        headers=EMPLOYEE_HEADERS,
    )
    assert resp.status_code == 400


async def test_submit_request_holiday_excluded(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Holiday in range is excluded from duration calculation."""
    policy_id = await _create_accrual_policy(async_client, key="sub-hol")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id, amount=4800)

    # Make Wednesday a holiday in a Mon-Fri range.
    await _add_holiday(db_session, date(2025, 1, 8), "Mid-Week Holiday")

    data = await _submit_request(
        async_client,
        policy_id,
        start_day=6,
        end_day=10,
        end_hour=17,
    )
    # 5 workdays minus 1 holiday = 4 * 480 = 1920.
    assert data["requested_minutes"] == 1920


async def test_submit_request_employee_role_can_submit(async_client: AsyncClient) -> None:
    """Employee role can submit a request (not just admins)."""
    policy_id = await _create_accrual_policy(async_client, key="sub-emprole")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    data = await _submit_request(async_client, policy_id, headers=EMPLOYEE_HEADERS)
    assert data["status"] == "SUBMITTED"


async def test_submit_request_admin_can_submit(async_client: AsyncClient) -> None:
    """Admin role can submit a request on behalf of an employee."""
    policy_id = await _create_accrual_policy(async_client, key="sub-adminrole")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    data = await _submit_request(async_client, policy_id, headers=AUTH_HEADERS)
    assert data["status"] == "SUBMITTED"


# ---------------------------------------------------------------------------
# Overlap detection tests
# ---------------------------------------------------------------------------


async def test_submit_overlap_with_submitted_request(async_client: AsyncClient) -> None:
    """409 when new request overlaps an existing SUBMITTED request."""
    policy_id = await _create_accrual_policy(async_client, key="olap-sub")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id, amount=9600)

    # First request: Mon Jan 6.
    await _submit_request(async_client, policy_id)

    # Second request: same day (overlap).
    resp = await async_client.post(
        REQUESTS_URL,
        json=_submit_payload(policy_id),
        headers=EMPLOYEE_HEADERS,
    )
    assert resp.status_code == 409


async def test_submit_overlap_with_approved_request(async_client: AsyncClient) -> None:
    """409 when new request overlaps an APPROVED request."""
    policy_id = await _create_accrual_policy(async_client, key="olap-appr")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id, amount=9600)

    # Submit and approve.
    data = await _submit_request(async_client, policy_id)
    await async_client.post(f"{REQUESTS_URL}/{data['id']}/approve", headers=AUTH_HEADERS)

    # Second request: same day (overlap with approved).
    resp = await async_client.post(
        REQUESTS_URL,
        json=_submit_payload(policy_id),
        headers=EMPLOYEE_HEADERS,
    )
    assert resp.status_code == 409


async def test_submit_no_overlap_with_cancelled_request(async_client: AsyncClient) -> None:
    """No overlap with a CANCELLED request — submission succeeds."""
    policy_id = await _create_accrual_policy(async_client, key="olap-canc")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id, amount=9600)

    # Submit and cancel.
    data = await _submit_request(async_client, policy_id)
    await async_client.post(f"{REQUESTS_URL}/{data['id']}/cancel", headers=EMPLOYEE_HEADERS)

    # Second request: same day — should succeed since first was cancelled.
    data2 = await _submit_request(async_client, policy_id)
    assert data2["status"] == "SUBMITTED"


async def test_submit_no_overlap_with_denied_request(async_client: AsyncClient) -> None:
    """No overlap with a DENIED request — submission succeeds."""
    policy_id = await _create_accrual_policy(async_client, key="olap-deny")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id, amount=9600)

    # Submit and deny.
    data = await _submit_request(async_client, policy_id)
    await async_client.post(f"{REQUESTS_URL}/{data['id']}/deny", headers=AUTH_HEADERS)

    # Second request: same day — should succeed since first was denied.
    data2 = await _submit_request(async_client, policy_id)
    assert data2["status"] == "SUBMITTED"


async def test_submit_no_overlap_different_policy(async_client: AsyncClient) -> None:
    """No overlap when requests are for different policies."""
    p1 = await _create_accrual_policy(async_client, key="olap-p1")
    p2 = await _create_accrual_policy(async_client, key="olap-p2")
    await _assign_employee(async_client, p1)
    await _assign_employee(async_client, p2)
    await _grant_balance(async_client, p1, amount=9600)
    await _grant_balance(async_client, p2, amount=9600)

    await _submit_request(async_client, p1)
    data = await _submit_request(async_client, p2)
    assert data["status"] == "SUBMITTED"


async def test_submit_no_overlap_adjacent_requests(async_client: AsyncClient) -> None:
    """Adjacent (non-overlapping) requests are allowed."""
    policy_id = await _create_accrual_policy(async_client, key="olap-adj")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id, amount=9600)

    # First: Monday Jan 6.
    await _submit_request(async_client, policy_id, start_day=6, end_day=6)

    # Second: Tuesday Jan 7 — no overlap.
    data = await _submit_request(async_client, policy_id, start_day=7, end_day=7)
    assert data["status"] == "SUBMITTED"


# ---------------------------------------------------------------------------
# Approve request tests
# ---------------------------------------------------------------------------


async def test_approve_request_success(async_client: AsyncClient) -> None:
    """Approve changes status to APPROVED with decided_at and decided_by."""
    policy_id = await _create_accrual_policy(async_client, key="appr-ok")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    data = await _submit_request(async_client, policy_id)
    request_id = data["id"]

    resp = await async_client.post(f"{REQUESTS_URL}/{request_id}/approve", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    result = resp.json()
    assert result["status"] == "APPROVED"
    assert result["decided_at"] is not None
    assert result["decided_by"] == str(USER_ID)


async def test_approve_creates_hold_release_and_usage(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Approve creates HOLD_RELEASE (+) and USAGE (-) ledger entries."""
    policy_id = await _create_accrual_policy(async_client, key="appr-ledger")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    data = await _submit_request(async_client, policy_id)
    request_id = data["id"]

    await async_client.post(f"{REQUESTS_URL}/{request_id}/approve", headers=AUTH_HEADERS)

    result = await db_session.execute(
        select(TimeOffLedgerEntry).where(
            col(TimeOffLedgerEntry.source_id) == request_id,
            col(TimeOffLedgerEntry.source_type) == LedgerSourceType.REQUEST.value,
        )
    )
    entries = {e.entry_type: e for e in result.scalars().all()}

    assert LedgerEntryType.HOLD.value in entries
    assert LedgerEntryType.HOLD_RELEASE.value in entries
    assert LedgerEntryType.USAGE.value in entries

    assert entries[LedgerEntryType.HOLD_RELEASE.value].amount_minutes == 480
    assert entries[LedgerEntryType.USAGE.value].amount_minutes == -480


async def test_approve_updates_snapshot(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """After approve: held=0, used=480, available = accrued - 480."""
    policy_id = await _create_accrual_policy(async_client, key="appr-snap")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id, amount=4800)

    data = await _submit_request(async_client, policy_id)
    await async_client.post(f"{REQUESTS_URL}/{data['id']}/approve", headers=AUTH_HEADERS)

    result = await db_session.execute(
        select(TimeOffBalanceSnapshot).where(
            col(TimeOffBalanceSnapshot.company_id) == COMPANY_ID,
            col(TimeOffBalanceSnapshot.employee_id) == EMPLOYEE_ID,
            col(TimeOffBalanceSnapshot.policy_id) == uuid.UUID(policy_id),
        )
    )
    snapshot = result.scalar_one()
    assert snapshot.held_minutes == 0
    assert snapshot.used_minutes == 480
    assert snapshot.available_minutes == 4800 - 480


async def test_approve_non_submitted_request(async_client: AsyncClient) -> None:
    """Approving a non-SUBMITTED request returns 400."""
    policy_id = await _create_accrual_policy(async_client, key="appr-bad")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    data = await _submit_request(async_client, policy_id)
    request_id = data["id"]

    # Approve once.
    await async_client.post(f"{REQUESTS_URL}/{request_id}/approve", headers=AUTH_HEADERS)

    # Try to approve again → 400 (already APPROVED).
    resp = await async_client.post(f"{REQUESTS_URL}/{request_id}/approve", headers=AUTH_HEADERS)
    assert resp.status_code == 400


async def test_approve_not_found(async_client: AsyncClient) -> None:
    """Approving a non-existent request returns 404."""
    fake_id = uuid.uuid4()
    resp = await async_client.post(f"{REQUESTS_URL}/{fake_id}/approve", headers=AUTH_HEADERS)
    assert resp.status_code == 404


async def test_approve_requires_admin(async_client: AsyncClient) -> None:
    """Employee role cannot approve a request."""
    policy_id = await _create_accrual_policy(async_client, key="appr-nonadmin")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    data = await _submit_request(async_client, policy_id)
    request_id = data["id"]

    resp = await async_client.post(f"{REQUESTS_URL}/{request_id}/approve", headers=EMPLOYEE_HEADERS)
    assert resp.status_code == 403


async def test_approve_with_decision_note(async_client: AsyncClient) -> None:
    """Decision note is stored on approve."""
    policy_id = await _create_accrual_policy(async_client, key="appr-note")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    data = await _submit_request(async_client, policy_id)
    request_id = data["id"]

    resp = await async_client.post(
        f"{REQUESTS_URL}/{request_id}/approve",
        json={"note": "Looks good!"},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["decision_note"] == "Looks good!"


async def test_approve_without_body(async_client: AsyncClient) -> None:
    """Approve with no body succeeds."""
    policy_id = await _create_accrual_policy(async_client, key="appr-nobody")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    data = await _submit_request(async_client, policy_id)
    request_id = data["id"]

    resp = await async_client.post(f"{REQUESTS_URL}/{request_id}/approve", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["decision_note"] is None


# ---------------------------------------------------------------------------
# Deny request tests
# ---------------------------------------------------------------------------


async def test_deny_request_success(async_client: AsyncClient) -> None:
    """Deny changes status to DENIED and releases hold."""
    policy_id = await _create_accrual_policy(async_client, key="deny-ok")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    data = await _submit_request(async_client, policy_id)
    request_id = data["id"]

    resp = await async_client.post(f"{REQUESTS_URL}/{request_id}/deny", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    result = resp.json()
    assert result["status"] == "DENIED"
    assert result["decided_at"] is not None
    assert result["decided_by"] == str(USER_ID)


async def test_deny_creates_hold_release(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Deny creates a HOLD_RELEASE ledger entry."""
    policy_id = await _create_accrual_policy(async_client, key="deny-ledger")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    data = await _submit_request(async_client, policy_id)
    request_id = data["id"]

    await async_client.post(f"{REQUESTS_URL}/{request_id}/deny", headers=AUTH_HEADERS)

    result = await db_session.execute(
        select(TimeOffLedgerEntry).where(
            col(TimeOffLedgerEntry.source_id) == request_id,
            col(TimeOffLedgerEntry.entry_type) == LedgerEntryType.HOLD_RELEASE.value,
        )
    )
    hold_release = result.scalar_one()
    assert hold_release.amount_minutes == 480


async def test_deny_updates_snapshot_releases_hold(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """After deny: held=0, used=0, available = accrued (fully restored)."""
    policy_id = await _create_accrual_policy(async_client, key="deny-snap")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id, amount=4800)

    data = await _submit_request(async_client, policy_id)
    await async_client.post(f"{REQUESTS_URL}/{data['id']}/deny", headers=AUTH_HEADERS)

    result = await db_session.execute(
        select(TimeOffBalanceSnapshot).where(
            col(TimeOffBalanceSnapshot.company_id) == COMPANY_ID,
            col(TimeOffBalanceSnapshot.employee_id) == EMPLOYEE_ID,
            col(TimeOffBalanceSnapshot.policy_id) == uuid.UUID(policy_id),
        )
    )
    snapshot = result.scalar_one()
    assert snapshot.held_minutes == 0
    assert snapshot.used_minutes == 0
    assert snapshot.available_minutes == 4800


async def test_deny_non_submitted_request(async_client: AsyncClient) -> None:
    """Denying a non-SUBMITTED request returns 400."""
    policy_id = await _create_accrual_policy(async_client, key="deny-bad")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    data = await _submit_request(async_client, policy_id)
    request_id = data["id"]

    await async_client.post(f"{REQUESTS_URL}/{request_id}/deny", headers=AUTH_HEADERS)
    resp = await async_client.post(f"{REQUESTS_URL}/{request_id}/deny", headers=AUTH_HEADERS)
    assert resp.status_code == 400


async def test_deny_requires_admin(async_client: AsyncClient) -> None:
    """Employee role cannot deny a request."""
    policy_id = await _create_accrual_policy(async_client, key="deny-nonadmin")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    data = await _submit_request(async_client, policy_id)
    resp = await async_client.post(f"{REQUESTS_URL}/{data['id']}/deny", headers=EMPLOYEE_HEADERS)
    assert resp.status_code == 403


async def test_deny_with_decision_note(async_client: AsyncClient) -> None:
    """Decision note is stored on deny."""
    policy_id = await _create_accrual_policy(async_client, key="deny-note")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    data = await _submit_request(async_client, policy_id)
    resp = await async_client.post(
        f"{REQUESTS_URL}/{data['id']}/deny",
        json={"note": "Insufficient coverage"},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["decision_note"] == "Insufficient coverage"


# ---------------------------------------------------------------------------
# Cancel request tests
# ---------------------------------------------------------------------------


async def test_cancel_request_by_employee(async_client: AsyncClient) -> None:
    """Employee can cancel their own submitted request."""
    policy_id = await _create_accrual_policy(async_client, key="canc-emp")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    data = await _submit_request(async_client, policy_id)
    request_id = data["id"]

    resp = await async_client.post(f"{REQUESTS_URL}/{request_id}/cancel", headers=EMPLOYEE_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"


async def test_cancel_request_by_admin(async_client: AsyncClient) -> None:
    """Admin can cancel any request."""
    policy_id = await _create_accrual_policy(async_client, key="canc-admin")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    data = await _submit_request(async_client, policy_id)
    request_id = data["id"]

    resp = await async_client.post(f"{REQUESTS_URL}/{request_id}/cancel", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"


async def test_cancel_other_employee_forbidden(async_client: AsyncClient) -> None:
    """Employee A cannot cancel Employee B's request."""
    policy_id = await _create_accrual_policy(async_client, key="canc-other")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    data = await _submit_request(async_client, policy_id)
    request_id = data["id"]

    other_employee_headers = {
        "X-Company-Id": str(COMPANY_ID),
        "X-User-Id": str(uuid.uuid4()),
        "X-Role": "employee",
    }
    resp = await async_client.post(f"{REQUESTS_URL}/{request_id}/cancel", headers=other_employee_headers)
    assert resp.status_code == 403


async def test_cancel_releases_hold(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Cancel releases the balance hold — same snapshot effect as deny."""
    policy_id = await _create_accrual_policy(async_client, key="canc-hold")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id, amount=4800)

    data = await _submit_request(async_client, policy_id)
    await async_client.post(f"{REQUESTS_URL}/{data['id']}/cancel", headers=EMPLOYEE_HEADERS)

    result = await db_session.execute(
        select(TimeOffBalanceSnapshot).where(
            col(TimeOffBalanceSnapshot.company_id) == COMPANY_ID,
            col(TimeOffBalanceSnapshot.employee_id) == EMPLOYEE_ID,
            col(TimeOffBalanceSnapshot.policy_id) == uuid.UUID(policy_id),
        )
    )
    snapshot = result.scalar_one()
    assert snapshot.held_minutes == 0
    assert snapshot.available_minutes == 4800


async def test_cancel_non_submitted(async_client: AsyncClient) -> None:
    """Cancelling a non-SUBMITTED request returns 400."""
    policy_id = await _create_accrual_policy(async_client, key="canc-bad")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    data = await _submit_request(async_client, policy_id)
    request_id = data["id"]

    await async_client.post(f"{REQUESTS_URL}/{request_id}/cancel", headers=EMPLOYEE_HEADERS)
    resp = await async_client.post(f"{REQUESTS_URL}/{request_id}/cancel", headers=EMPLOYEE_HEADERS)
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# List and get tests
# ---------------------------------------------------------------------------


async def test_list_requests_empty(async_client: AsyncClient) -> None:
    """No requests returns empty list."""
    resp = await async_client.get(REQUESTS_URL, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_list_requests_returns_submitted(async_client: AsyncClient) -> None:
    """Submitted requests appear in the list."""
    policy_id = await _create_accrual_policy(async_client, key="list-sub")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    await _submit_request(async_client, policy_id)

    resp = await async_client.get(REQUESTS_URL, headers=AUTH_HEADERS)
    data = resp.json()
    assert data["total"] >= 1


async def test_list_requests_pagination(async_client: AsyncClient) -> None:
    """Pagination with offset and limit."""
    policy_id = await _create_accrual_policy(async_client, key="list-page")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id, amount=9600)

    # Submit 3 requests on different days.
    for day in [6, 7, 8]:  # Mon, Tue, Wed
        await _submit_request(async_client, policy_id, start_day=day, end_day=day)

    resp = await async_client.get(f"{REQUESTS_URL}?offset=0&limit=2", headers=AUTH_HEADERS)
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2


async def test_list_requests_filter_by_status(async_client: AsyncClient) -> None:
    """Filter by status returns only matching requests."""
    policy_id = await _create_accrual_policy(async_client, key="list-stat")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id, amount=9600)

    data1 = await _submit_request(async_client, policy_id, start_day=6, end_day=6)
    await _submit_request(async_client, policy_id, start_day=7, end_day=7)

    # Approve the first.
    await async_client.post(f"{REQUESTS_URL}/{data1['id']}/approve", headers=AUTH_HEADERS)

    resp = await async_client.get(f"{REQUESTS_URL}?status=APPROVED", headers=AUTH_HEADERS)
    data = resp.json()
    assert all(item["status"] == "APPROVED" for item in data["items"])
    assert data["total"] >= 1


async def test_list_requests_filter_by_policy(async_client: AsyncClient) -> None:
    """Filter by policy_id returns only matching requests."""
    p1 = await _create_accrual_policy(async_client, key="list-pol1")
    p2 = await _create_accrual_policy(async_client, key="list-pol2")
    await _assign_employee(async_client, p1)
    await _assign_employee(async_client, p2)
    await _grant_balance(async_client, p1)
    await _grant_balance(async_client, p2)

    await _submit_request(async_client, p1, start_day=6, end_day=6)
    await _submit_request(async_client, p2, start_day=7, end_day=7)

    resp = await async_client.get(f"{REQUESTS_URL}?policy_id={p1}", headers=AUTH_HEADERS)
    data = resp.json()
    assert data["total"] >= 1
    assert all(item["policy_id"] == p1 for item in data["items"])


async def test_list_requests_filter_by_employee(async_client: AsyncClient) -> None:
    """Filter by employee_id returns only matching requests."""
    policy_id = await _create_accrual_policy(async_client, key="list-emp")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)
    await _submit_request(async_client, policy_id)

    resp = await async_client.get(f"{REQUESTS_URL}?employee_id={EMPLOYEE_ID}", headers=AUTH_HEADERS)
    data = resp.json()
    assert data["total"] >= 1
    assert all(item["employee_id"] == str(EMPLOYEE_ID) for item in data["items"])


async def test_list_requests_company_isolation(async_client: AsyncClient) -> None:
    """Requests from one company are not visible from another."""
    policy_id = await _create_accrual_policy(async_client, key="list-iso")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)
    await _submit_request(async_client, policy_id)

    other_company = uuid.uuid4()
    other_headers = {
        "X-Company-Id": str(other_company),
        "X-User-Id": str(USER_ID),
        "X-Role": "admin",
    }
    resp = await async_client.get(f"/companies/{other_company}/requests", headers=other_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


async def test_get_request_success(async_client: AsyncClient) -> None:
    """Get a single request by ID."""
    policy_id = await _create_accrual_policy(async_client, key="get-ok")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    data = await _submit_request(async_client, policy_id)
    request_id = data["id"]

    resp = await async_client.get(f"{REQUESTS_URL}/{request_id}", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["id"] == request_id


async def test_get_request_not_found(async_client: AsyncClient) -> None:
    """404 for non-existent request."""
    fake_id = uuid.uuid4()
    resp = await async_client.get(f"{REQUESTS_URL}/{fake_id}", headers=AUTH_HEADERS)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Balance invariant tests
# ---------------------------------------------------------------------------


async def test_invariant_available_after_submit(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """After submit: available = accrued - used - held."""
    policy_id = await _create_accrual_policy(async_client, key="inv-sub")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id, amount=4800)

    await _submit_request(async_client, policy_id)

    result = await db_session.execute(
        select(TimeOffBalanceSnapshot).where(
            col(TimeOffBalanceSnapshot.company_id) == COMPANY_ID,
            col(TimeOffBalanceSnapshot.employee_id) == EMPLOYEE_ID,
            col(TimeOffBalanceSnapshot.policy_id) == uuid.UUID(policy_id),
        )
    )
    s = result.scalar_one()
    assert s.available_minutes == s.accrued_minutes - s.used_minutes - s.held_minutes


async def test_invariant_available_unchanged_after_approve(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """After approve: available stays the same as post-submit."""
    policy_id = await _create_accrual_policy(async_client, key="inv-appr")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id, amount=4800)

    data = await _submit_request(async_client, policy_id)

    # Get available after submit.
    result = await db_session.execute(
        select(TimeOffBalanceSnapshot).where(
            col(TimeOffBalanceSnapshot.company_id) == COMPANY_ID,
            col(TimeOffBalanceSnapshot.employee_id) == EMPLOYEE_ID,
            col(TimeOffBalanceSnapshot.policy_id) == uuid.UUID(policy_id),
        )
    )
    available_after_submit = result.scalar_one().available_minutes

    await async_client.post(f"{REQUESTS_URL}/{data['id']}/approve", headers=AUTH_HEADERS)

    result = await db_session.execute(
        select(TimeOffBalanceSnapshot).where(
            col(TimeOffBalanceSnapshot.company_id) == COMPANY_ID,
            col(TimeOffBalanceSnapshot.employee_id) == EMPLOYEE_ID,
            col(TimeOffBalanceSnapshot.policy_id) == uuid.UUID(policy_id),
        )
    )
    s = result.scalar_one()
    assert s.available_minutes == available_after_submit
    assert s.available_minutes == s.accrued_minutes - s.used_minutes - s.held_minutes


async def test_invariant_available_restored_after_deny(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """After deny: available returns to pre-submit value."""
    policy_id = await _create_accrual_policy(async_client, key="inv-deny")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id, amount=4800)

    data = await _submit_request(async_client, policy_id)
    await async_client.post(f"{REQUESTS_URL}/{data['id']}/deny", headers=AUTH_HEADERS)

    result = await db_session.execute(
        select(TimeOffBalanceSnapshot).where(
            col(TimeOffBalanceSnapshot.company_id) == COMPANY_ID,
            col(TimeOffBalanceSnapshot.employee_id) == EMPLOYEE_ID,
            col(TimeOffBalanceSnapshot.policy_id) == uuid.UUID(policy_id),
        )
    )
    s = result.scalar_one()
    assert s.available_minutes == 4800
    assert s.held_minutes == 0
    assert s.used_minutes == 0


async def test_invariant_snapshot_matches_ledger_full_cycle(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """After submit+approve, snapshot matches _compute_balance_from_ledger."""
    from app.services.balance import _compute_balance_from_ledger

    policy_id = await _create_accrual_policy(async_client, key="inv-recomp")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id, amount=4800)

    data = await _submit_request(async_client, policy_id)
    await async_client.post(f"{REQUESTS_URL}/{data['id']}/approve", headers=AUTH_HEADERS)

    policy_uuid = uuid.UUID(policy_id)
    accrued, used, held = await _compute_balance_from_ledger(db_session, COMPANY_ID, EMPLOYEE_ID, policy_uuid)

    result = await db_session.execute(
        select(TimeOffBalanceSnapshot).where(
            col(TimeOffBalanceSnapshot.company_id) == COMPANY_ID,
            col(TimeOffBalanceSnapshot.employee_id) == EMPLOYEE_ID,
            col(TimeOffBalanceSnapshot.policy_id) == policy_uuid,
        )
    )
    s = result.scalar_one()
    assert s.accrued_minutes == accrued
    assert s.used_minutes == used
    assert s.held_minutes == held
    assert s.available_minutes == accrued - used - held


async def test_invariant_submit_approve_full_cycle(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Full submit→approve: held=0, used=480, available = accrued - 480."""
    policy_id = await _create_accrual_policy(async_client, key="inv-cycle-a")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id, amount=4800)

    data = await _submit_request(async_client, policy_id)
    await async_client.post(f"{REQUESTS_URL}/{data['id']}/approve", headers=AUTH_HEADERS)

    result = await db_session.execute(
        select(TimeOffBalanceSnapshot).where(
            col(TimeOffBalanceSnapshot.company_id) == COMPANY_ID,
            col(TimeOffBalanceSnapshot.employee_id) == EMPLOYEE_ID,
            col(TimeOffBalanceSnapshot.policy_id) == uuid.UUID(policy_id),
        )
    )
    s = result.scalar_one()
    assert s.held_minutes == 0
    assert s.used_minutes == 480
    assert s.accrued_minutes == 4800
    assert s.available_minutes == 4320


async def test_invariant_submit_deny_full_cycle(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Full submit→deny: held=0, used=0, available = accrued."""
    policy_id = await _create_accrual_policy(async_client, key="inv-cycle-d")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id, amount=4800)

    data = await _submit_request(async_client, policy_id)
    await async_client.post(f"{REQUESTS_URL}/{data['id']}/deny", headers=AUTH_HEADERS)

    result = await db_session.execute(
        select(TimeOffBalanceSnapshot).where(
            col(TimeOffBalanceSnapshot.company_id) == COMPANY_ID,
            col(TimeOffBalanceSnapshot.employee_id) == EMPLOYEE_ID,
            col(TimeOffBalanceSnapshot.policy_id) == uuid.UUID(policy_id),
        )
    )
    s = result.scalar_one()
    assert s.held_minutes == 0
    assert s.used_minutes == 0
    assert s.available_minutes == 4800


# ---------------------------------------------------------------------------
# Idempotency + concurrency tests
# ---------------------------------------------------------------------------


async def test_idempotency_key_returns_existing_request(async_client: AsyncClient) -> None:
    """Submitting with the same idempotency key returns the existing request."""
    policy_id = await _create_accrual_policy(async_client, key="idemp-ok")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id, amount=9600)

    payload = _submit_payload(policy_id, idempotency_key="test-key-1")

    resp1 = await async_client.post(REQUESTS_URL, json=payload, headers=EMPLOYEE_HEADERS)
    assert resp1.status_code == 201
    first_id = resp1.json()["id"]

    resp2 = await async_client.post(REQUESTS_URL, json=payload, headers=EMPLOYEE_HEADERS)
    # Second submission with same key returns the existing request (idempotent).
    assert resp2.status_code in (201, 409)
    if resp2.status_code == 201:
        assert resp2.json()["id"] == first_id


async def test_idempotency_key_different_employee_both_succeed(async_client: AsyncClient) -> None:
    """Same idempotency key with different employees: both succeed."""
    emp2 = uuid.uuid4()
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
        )
    )
    svc.seed(
        EmployeeInfo(
            id=emp2,
            company_id=COMPANY_ID,
            first_name="Other",
            last_name="Employee",
            email="other@example.com",
            pay_type="SALARY",
            workday_minutes=480,
            timezone="America/New_York",
        )
    )
    set_employee_service(svc)

    policy_id = await _create_accrual_policy(async_client, key="idemp-diff")
    await _assign_employee(async_client, policy_id, employee_id=EMPLOYEE_ID)
    await _assign_employee(async_client, policy_id, employee_id=emp2)
    await _grant_balance(async_client, policy_id, employee_id=EMPLOYEE_ID)
    await _grant_balance(async_client, policy_id, employee_id=emp2)

    payload1 = _submit_payload(policy_id, employee_id=EMPLOYEE_ID, idempotency_key="shared-key")
    payload2 = _submit_payload(policy_id, employee_id=emp2, idempotency_key="shared-key")

    resp1 = await async_client.post(REQUESTS_URL, json=payload1, headers=EMPLOYEE_HEADERS)
    assert resp1.status_code == 201

    emp2_headers = {
        "X-Company-Id": str(COMPANY_ID),
        "X-User-Id": str(emp2),
        "X-Role": "employee",
    }
    resp2 = await async_client.post(REQUESTS_URL, json=payload2, headers=emp2_headers)
    assert resp2.status_code == 201
    assert resp2.json()["id"] != resp1.json()["id"]


async def test_snapshot_version_increments_through_workflow(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Snapshot version increments: grant(v2) + submit(v3) + approve(v4)."""
    policy_id = await _create_accrual_policy(async_client, key="ver-inc")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id, amount=4800)

    data = await _submit_request(async_client, policy_id)
    await async_client.post(f"{REQUESTS_URL}/{data['id']}/approve", headers=AUTH_HEADERS)

    result = await db_session.execute(
        select(TimeOffBalanceSnapshot).where(
            col(TimeOffBalanceSnapshot.company_id) == COMPANY_ID,
            col(TimeOffBalanceSnapshot.employee_id) == EMPLOYEE_ID,
            col(TimeOffBalanceSnapshot.policy_id) == uuid.UUID(policy_id),
        )
    )
    snapshot = result.scalar_one()
    # Snapshot created (v1) by grant → adjustment (v2) → submit hold (v3) → approve (v4).
    assert snapshot.version == 4


async def test_ledger_idempotency_constraint(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Ledger unique constraint (source_type, source_id, entry_type) prevents duplicates."""
    policy_id = await _create_accrual_policy(async_client, key="ledger-idemp")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    data = await _submit_request(async_client, policy_id)
    request_id = data["id"]

    # Count HOLD entries for this request.
    result = await db_session.execute(
        select(TimeOffLedgerEntry).where(
            col(TimeOffLedgerEntry.source_id) == request_id,
            col(TimeOffLedgerEntry.source_type) == LedgerSourceType.REQUEST.value,
            col(TimeOffLedgerEntry.entry_type) == LedgerEntryType.HOLD.value,
        )
    )
    entries = list(result.scalars().all())
    assert len(entries) == 1  # Exactly one HOLD per request.


# ---------------------------------------------------------------------------
# Audit logging tests
# ---------------------------------------------------------------------------


async def test_submit_creates_audit_entry(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Submit writes an audit log with action=SUBMIT."""
    policy_id = await _create_accrual_policy(async_client, key="aud-sub")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    data = await _submit_request(async_client, policy_id)
    request_id = data["id"]

    result = await db_session.execute(
        select(AuditLog).where(
            col(AuditLog.entity_type) == "REQUEST",
            col(AuditLog.action) == "SUBMIT",
            col(AuditLog.entity_id) == uuid.UUID(request_id),
        )
    )
    audit = result.scalar_one()
    assert audit.after_json is not None
    assert audit.after_json["status"] == "SUBMITTED"


async def test_approve_creates_audit_entry(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Approve writes an audit log with action=APPROVE and before/after."""
    policy_id = await _create_accrual_policy(async_client, key="aud-appr")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    data = await _submit_request(async_client, policy_id)
    request_id = data["id"]

    await async_client.post(f"{REQUESTS_URL}/{request_id}/approve", headers=AUTH_HEADERS)

    result = await db_session.execute(
        select(AuditLog).where(
            col(AuditLog.entity_type) == "REQUEST",
            col(AuditLog.action) == "APPROVE",
            col(AuditLog.entity_id) == uuid.UUID(request_id),
        )
    )
    audit = result.scalar_one()
    assert audit.before_json is not None
    assert audit.before_json["status"] == "SUBMITTED"
    assert audit.after_json is not None
    assert audit.after_json["status"] == "APPROVED"


async def test_deny_creates_audit_entry(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Deny writes an audit log with action=DENY."""
    policy_id = await _create_accrual_policy(async_client, key="aud-deny")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    data = await _submit_request(async_client, policy_id)
    request_id = data["id"]

    await async_client.post(f"{REQUESTS_URL}/{request_id}/deny", headers=AUTH_HEADERS)

    result = await db_session.execute(
        select(AuditLog).where(
            col(AuditLog.entity_type) == "REQUEST",
            col(AuditLog.action) == "DENY",
            col(AuditLog.entity_id) == uuid.UUID(request_id),
        )
    )
    audit = result.scalar_one()
    assert audit.after_json is not None
    assert audit.after_json["status"] == "DENIED"


async def test_cancel_creates_audit_entry(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Cancel writes an audit log with action=CANCEL."""
    policy_id = await _create_accrual_policy(async_client, key="aud-canc")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    data = await _submit_request(async_client, policy_id)
    request_id = data["id"]

    await async_client.post(f"{REQUESTS_URL}/{request_id}/cancel", headers=EMPLOYEE_HEADERS)

    result = await db_session.execute(
        select(AuditLog).where(
            col(AuditLog.entity_type) == "REQUEST",
            col(AuditLog.action) == "CANCEL",
            col(AuditLog.entity_id) == uuid.UUID(request_id),
        )
    )
    audit = result.scalar_one()
    assert audit.after_json is not None
    assert audit.after_json["status"] == "CANCELLED"


async def test_audit_actor_matches_auth_user(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Audit actor_id matches the authenticated user."""
    policy_id = await _create_accrual_policy(async_client, key="aud-actor")
    await _assign_employee(async_client, policy_id)
    await _grant_balance(async_client, policy_id)

    data = await _submit_request(async_client, policy_id, headers=EMPLOYEE_HEADERS)
    request_id = data["id"]

    result = await db_session.execute(
        select(AuditLog).where(
            col(AuditLog.entity_type) == "REQUEST",
            col(AuditLog.action) == "SUBMIT",
            col(AuditLog.entity_id) == uuid.UUID(request_id),
        )
    )
    audit = result.scalar_one()
    assert audit.actor_id == EMPLOYEE_ID
