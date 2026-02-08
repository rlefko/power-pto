"""Comprehensive tests for balance reads, ledger queries, admin adjustments, invariants, and audit."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlmodel import col

from app.models.audit import AuditLog
from app.models.balance import TimeOffBalanceSnapshot
from app.models.enums import LedgerEntryType, LedgerSourceType
from app.models.ledger import TimeOffLedgerEntry
from app.models.policy import TimeOffPolicy, TimeOffPolicyVersion

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

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


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


async def _create_accrual_policy(
    client: AsyncClient,
    key: str = "vacation-accrual",
    allow_negative: bool = False,
    negative_limit_minutes: int | None = None,
    bank_cap_minutes: int | None = None,
) -> str:
    """Create a time-based accrual policy and return its ID."""
    settings: dict = {  # type: ignore[type-arg]
        "type": "ACCRUAL",
        "accrual_method": "TIME",
        "accrual_frequency": "MONTHLY",
        "accrual_timing": "START_OF_PERIOD",
        "rate_minutes_per_month": 480,
        "allow_negative": allow_negative,
    }
    if negative_limit_minutes is not None:
        settings["negative_limit_minutes"] = negative_limit_minutes
    if bank_cap_minutes is not None:
        settings["bank_cap_minutes"] = bank_cap_minutes
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


async def _create_unlimited_policy(client: AsyncClient, key: str = "vacation-unlimited") -> str:
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
) -> str:
    """Assign employee to policy and return assignment ID."""
    resp = await client.post(
        f"{POLICIES_URL}/{policy_id}/assignments",
        json={"employee_id": str(employee_id), "effective_from": "2025-01-01"},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201
    assignment_id: str = resp.json()["id"]
    return assignment_id


def _adjustment_url() -> str:
    return f"/companies/{COMPANY_ID}/adjustments"


def _adjustment_payload(
    employee_id: uuid.UUID = EMPLOYEE_ID,
    policy_id: str = "",
    amount_minutes: int = 480,
    reason: str = "Test adjustment",
) -> dict:  # type: ignore[type-arg]
    return {
        "employee_id": str(employee_id),
        "policy_id": policy_id,
        "amount_minutes": amount_minutes,
        "reason": reason,
    }


def _balances_url(employee_id: uuid.UUID = EMPLOYEE_ID) -> str:
    return f"/companies/{COMPANY_ID}/employees/{employee_id}/balances"


def _ledger_url(employee_id: uuid.UUID = EMPLOYEE_ID) -> str:
    return f"/companies/{COMPANY_ID}/employees/{employee_id}/ledger"


# ---------------------------------------------------------------------------
# GET balances (read path)
# ---------------------------------------------------------------------------


async def test_get_balances_empty_no_assignments(async_client: AsyncClient) -> None:
    """Employee with no assignments returns empty balance list."""
    emp = uuid.uuid4()
    resp = await async_client.get(_balances_url(emp), headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_get_balances_zero_with_assignment(async_client: AsyncClient) -> None:
    """Employee assigned to a policy but with no ledger entries returns zero balance."""
    policy_id = await _create_accrual_policy(async_client)
    await _assign_employee(async_client, policy_id)

    resp = await async_client.get(_balances_url(), headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1

    balance = next(b for b in data["items"] if b["policy_id"] == policy_id)
    assert balance["accrued_minutes"] == 0
    assert balance["used_minutes"] == 0
    assert balance["held_minutes"] == 0
    assert balance["available_minutes"] == 0
    assert balance["is_unlimited"] is False


async def test_get_balances_after_positive_adjustment(async_client: AsyncClient) -> None:
    """Balance reflects a positive adjustment."""
    policy_id = await _create_accrual_policy(async_client, key="vacation-pos")
    await _assign_employee(async_client, policy_id)

    # Create a +480 adjustment.
    resp = await async_client.post(
        _adjustment_url(),
        json=_adjustment_payload(policy_id=policy_id, amount_minutes=480),
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201

    # Read balances.
    resp = await async_client.get(_balances_url(), headers=AUTH_HEADERS)
    assert resp.status_code == 200
    balance = next(b for b in resp.json()["items"] if b["policy_id"] == policy_id)
    assert balance["accrued_minutes"] == 480
    assert balance["available_minutes"] == 480
    assert balance["used_minutes"] == 0
    assert balance["held_minutes"] == 0


async def test_get_balances_multiple_policies(async_client: AsyncClient) -> None:
    """Employee assigned to two policies gets separate balances."""
    emp = uuid.uuid4()
    p1 = await _create_accrual_policy(async_client, key="multi-vac")
    p2 = await _create_accrual_policy(async_client, key="multi-sick")
    await _assign_employee(async_client, p1, employee_id=emp)
    await _assign_employee(async_client, p2, employee_id=emp)

    # Adjust p1 by +480, p2 by +240.
    await async_client.post(
        _adjustment_url(),
        json=_adjustment_payload(employee_id=emp, policy_id=p1, amount_minutes=480),
        headers=AUTH_HEADERS,
    )
    await async_client.post(
        _adjustment_url(),
        json=_adjustment_payload(employee_id=emp, policy_id=p2, amount_minutes=240),
        headers=AUTH_HEADERS,
    )

    resp = await async_client.get(_balances_url(emp), headers=AUTH_HEADERS)
    data = resp.json()
    assert data["total"] == 2

    b1 = next(b for b in data["items"] if b["policy_id"] == p1)
    b2 = next(b for b in data["items"] if b["policy_id"] == p2)
    assert b1["accrued_minutes"] == 480
    assert b2["accrued_minutes"] == 240


async def test_get_balances_unlimited_policy(async_client: AsyncClient) -> None:
    """Unlimited policy returns is_unlimited=True and available_minutes=None."""
    emp = uuid.uuid4()
    policy_id = await _create_unlimited_policy(async_client, key="unlimited-bal")
    await _assign_employee(async_client, policy_id, employee_id=emp)

    resp = await async_client.get(_balances_url(emp), headers=AUTH_HEADERS)
    balance = next(b for b in resp.json()["items"] if b["policy_id"] == policy_id)
    assert balance["is_unlimited"] is True
    assert balance["available_minutes"] is None


async def test_get_balances_includes_policy_metadata(async_client: AsyncClient) -> None:
    """Balance response includes policy key and category."""
    emp = uuid.uuid4()
    policy_id = await _create_accrual_policy(async_client, key="meta-test")
    await _assign_employee(async_client, policy_id, employee_id=emp)

    resp = await async_client.get(_balances_url(emp), headers=AUTH_HEADERS)
    balance = next(b for b in resp.json()["items"] if b["policy_id"] == policy_id)
    assert balance["policy_key"] == "meta-test"
    assert balance["policy_category"] == "VACATION"


async def test_get_balances_employee_role_can_read(async_client: AsyncClient) -> None:
    """Non-admin (employee role) can read balances."""
    emp = uuid.uuid4()
    policy_id = await _create_accrual_policy(async_client, key="emp-read")
    await _assign_employee(async_client, policy_id, employee_id=emp)

    headers = {
        "X-Company-Id": str(COMPANY_ID),
        "X-User-Id": str(emp),
        "X-Role": "employee",
    }
    resp = await async_client.get(_balances_url(emp), headers=headers)
    assert resp.status_code == 200


async def test_get_balances_company_isolation(async_client: AsyncClient) -> None:
    """Balances for one company are not visible from another company."""
    policy_id = await _create_accrual_policy(async_client, key="iso-test")
    await _assign_employee(async_client, policy_id)
    await async_client.post(
        _adjustment_url(),
        json=_adjustment_payload(policy_id=policy_id, amount_minutes=480),
        headers=AUTH_HEADERS,
    )

    other_company = uuid.uuid4()
    other_headers = {
        "X-Company-Id": str(other_company),
        "X-User-Id": str(USER_ID),
        "X-Role": "admin",
    }
    resp = await async_client.get(
        f"/companies/{other_company}/employees/{EMPLOYEE_ID}/balances",
        headers=other_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# GET ledger (read path)
# ---------------------------------------------------------------------------


async def test_get_ledger_empty(async_client: AsyncClient) -> None:
    """No ledger entries returns empty list."""
    emp = uuid.uuid4()
    policy_id = await _create_accrual_policy(async_client, key="ledger-empty")
    await _assign_employee(async_client, policy_id, employee_id=emp)

    resp = await async_client.get(f"{_ledger_url(emp)}?policy_id={policy_id}", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_get_ledger_after_adjustment(async_client: AsyncClient) -> None:
    """Ledger shows the adjustment entry with correct fields."""
    emp = uuid.uuid4()
    policy_id = await _create_accrual_policy(async_client, key="ledger-adj")
    await _assign_employee(async_client, policy_id, employee_id=emp)

    await async_client.post(
        _adjustment_url(),
        json=_adjustment_payload(employee_id=emp, policy_id=policy_id, amount_minutes=480, reason="Grant"),
        headers=AUTH_HEADERS,
    )

    resp = await async_client.get(f"{_ledger_url(emp)}?policy_id={policy_id}", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    entry = data["items"][0]
    assert entry["entry_type"] == "ADJUSTMENT"
    assert entry["amount_minutes"] == 480
    assert entry["source_type"] == "ADMIN"
    assert entry["metadata_json"]["reason"] == "Grant"


async def test_get_ledger_pagination(async_client: AsyncClient) -> None:
    """Ledger pagination with offset and limit."""
    emp = uuid.uuid4()
    policy_id = await _create_accrual_policy(async_client, key="ledger-page")
    await _assign_employee(async_client, policy_id, employee_id=emp)

    for i in range(3):
        await async_client.post(
            _adjustment_url(),
            json=_adjustment_payload(employee_id=emp, policy_id=policy_id, amount_minutes=100 + i, reason=f"adj {i}"),
            headers=AUTH_HEADERS,
        )

    resp = await async_client.get(f"{_ledger_url(emp)}?policy_id={policy_id}&offset=0&limit=2", headers=AUTH_HEADERS)
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2

    resp2 = await async_client.get(f"{_ledger_url(emp)}?policy_id={policy_id}&offset=2&limit=2", headers=AUTH_HEADERS)
    data2 = resp2.json()
    assert len(data2["items"]) == 1


async def test_get_ledger_ordered_by_effective_at_desc(async_client: AsyncClient) -> None:
    """Entries are returned newest first."""
    emp = uuid.uuid4()
    policy_id = await _create_accrual_policy(async_client, key="ledger-order")
    await _assign_employee(async_client, policy_id, employee_id=emp)

    for i in range(3):
        await async_client.post(
            _adjustment_url(),
            json=_adjustment_payload(employee_id=emp, policy_id=policy_id, amount_minutes=100 * (i + 1)),
            headers=AUTH_HEADERS,
        )

    resp = await async_client.get(f"{_ledger_url(emp)}?policy_id={policy_id}", headers=AUTH_HEADERS)
    items = resp.json()["items"]
    # Latest adjustment (300) should be first.
    assert items[0]["amount_minutes"] == 300
    assert items[-1]["amount_minutes"] == 100


async def test_get_ledger_requires_policy_id(async_client: AsyncClient) -> None:
    """Missing policy_id query param returns 422."""
    resp = await async_client.get(_ledger_url(), headers=AUTH_HEADERS)
    assert resp.status_code == 422


async def test_get_ledger_filters_by_policy(async_client: AsyncClient) -> None:
    """Entries for other policies are not returned."""
    emp = uuid.uuid4()
    p1 = await _create_accrual_policy(async_client, key="ledger-p1")
    p2 = await _create_accrual_policy(async_client, key="ledger-p2")
    await _assign_employee(async_client, p1, employee_id=emp)
    await _assign_employee(async_client, p2, employee_id=emp)

    await async_client.post(
        _adjustment_url(),
        json=_adjustment_payload(employee_id=emp, policy_id=p1, amount_minutes=100),
        headers=AUTH_HEADERS,
    )
    await async_client.post(
        _adjustment_url(),
        json=_adjustment_payload(employee_id=emp, policy_id=p2, amount_minutes=200),
        headers=AUTH_HEADERS,
    )

    resp = await async_client.get(f"{_ledger_url(emp)}?policy_id={p1}", headers=AUTH_HEADERS)
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["amount_minutes"] == 100


async def test_get_ledger_company_isolation(async_client: AsyncClient) -> None:
    """Ledger entries from one company are not visible to another."""
    emp = uuid.uuid4()
    policy_id = await _create_accrual_policy(async_client, key="ledger-iso")
    await _assign_employee(async_client, policy_id, employee_id=emp)
    await async_client.post(
        _adjustment_url(),
        json=_adjustment_payload(employee_id=emp, policy_id=policy_id, amount_minutes=480),
        headers=AUTH_HEADERS,
    )

    other_company = uuid.uuid4()
    other_headers = {
        "X-Company-Id": str(other_company),
        "X-User-Id": str(USER_ID),
        "X-Role": "admin",
    }
    resp = await async_client.get(
        f"/companies/{other_company}/employees/{emp}/ledger?policy_id={policy_id}",
        headers=other_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# POST adjustments (write path)
# ---------------------------------------------------------------------------


async def test_create_positive_adjustment(async_client: AsyncClient) -> None:
    """Basic positive adjustment succeeds."""
    policy_id = await _create_accrual_policy(async_client, key="adj-pos")
    await _assign_employee(async_client, policy_id)

    resp = await async_client.post(
        _adjustment_url(),
        json=_adjustment_payload(policy_id=policy_id, amount_minutes=960, reason="Initial grant"),
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["entry_type"] == "ADJUSTMENT"
    assert data["amount_minutes"] == 960
    assert data["source_type"] == "ADMIN"
    assert data["metadata_json"]["reason"] == "Initial grant"


async def test_create_negative_adjustment_sufficient_balance(async_client: AsyncClient) -> None:
    """Negative adjustment succeeds when prior balance is sufficient."""
    policy_id = await _create_accrual_policy(async_client, key="adj-neg-ok")
    await _assign_employee(async_client, policy_id)

    # Grant +960 first.
    await async_client.post(
        _adjustment_url(),
        json=_adjustment_payload(policy_id=policy_id, amount_minutes=960),
        headers=AUTH_HEADERS,
    )

    # Deduct -480.
    resp = await async_client.post(
        _adjustment_url(),
        json=_adjustment_payload(policy_id=policy_id, amount_minutes=-480, reason="Correction"),
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201
    assert resp.json()["amount_minutes"] == -480


async def test_create_negative_adjustment_insufficient_balance(async_client: AsyncClient) -> None:
    """Negative adjustment blocked when insufficient balance and allow_negative=false."""
    policy_id = await _create_accrual_policy(async_client, key="adj-neg-fail")
    await _assign_employee(async_client, policy_id)

    resp = await async_client.post(
        _adjustment_url(),
        json=_adjustment_payload(policy_id=policy_id, amount_minutes=-480, reason="Debit"),
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 400


async def test_create_negative_adjustment_with_allow_negative(async_client: AsyncClient) -> None:
    """Negative adjustment allowed when allow_negative=true."""
    policy_id = await _create_accrual_policy(
        async_client, key="adj-neg-allow", allow_negative=True, negative_limit_minutes=960
    )
    await _assign_employee(async_client, policy_id)

    resp = await async_client.post(
        _adjustment_url(),
        json=_adjustment_payload(policy_id=policy_id, amount_minutes=-480, reason="Allowed debit"),
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201

    # Verify the balance is negative.
    bal_resp = await async_client.get(_balances_url(), headers=AUTH_HEADERS)
    balance = next(b for b in bal_resp.json()["items"] if b["policy_id"] == policy_id)
    assert balance["available_minutes"] == -480


async def test_create_negative_adjustment_exceeds_limit(async_client: AsyncClient) -> None:
    """Negative adjustment rejected when exceeding negative_limit_minutes."""
    policy_id = await _create_accrual_policy(
        async_client, key="adj-neg-limit", allow_negative=True, negative_limit_minutes=960
    )
    await _assign_employee(async_client, policy_id)

    resp = await async_client.post(
        _adjustment_url(),
        json=_adjustment_payload(policy_id=policy_id, amount_minutes=-1440, reason="Too much"),
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 400


async def test_create_negative_adjustment_no_limit(async_client: AsyncClient) -> None:
    """Negative adjustment allowed without limit when allow_negative=true and no limit set."""
    policy_id = await _create_accrual_policy(async_client, key="adj-neg-nolim", allow_negative=True)
    await _assign_employee(async_client, policy_id)

    resp = await async_client.post(
        _adjustment_url(),
        json=_adjustment_payload(policy_id=policy_id, amount_minutes=-9999, reason="Deep negative"),
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201


async def test_create_adjustment_no_active_assignment(async_client: AsyncClient) -> None:
    """Adjustment fails when employee has no active assignment."""
    policy_id = await _create_accrual_policy(async_client, key="adj-no-assign")

    resp = await async_client.post(
        _adjustment_url(),
        json=_adjustment_payload(policy_id=policy_id, amount_minutes=480),
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 400


async def test_create_adjustment_non_admin_forbidden(async_client: AsyncClient) -> None:
    """Employee role cannot create adjustments."""
    policy_id = await _create_accrual_policy(async_client, key="adj-nonadmin")
    await _assign_employee(async_client, policy_id)

    resp = await async_client.post(
        _adjustment_url(),
        json=_adjustment_payload(policy_id=policy_id, amount_minutes=480),
        headers=EMPLOYEE_HEADERS,
    )
    assert resp.status_code == 403


async def test_create_adjustment_missing_reason(async_client: AsyncClient) -> None:
    """Missing or empty reason returns 422."""
    policy_id = await _create_accrual_policy(async_client, key="adj-noreason")
    await _assign_employee(async_client, policy_id)

    resp = await async_client.post(
        _adjustment_url(),
        json={
            "employee_id": str(EMPLOYEE_ID),
            "policy_id": policy_id,
            "amount_minutes": 480,
            "reason": "",
        },
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 422


async def test_create_adjustment_unlimited_policy(async_client: AsyncClient) -> None:
    """Adjustment to unlimited policy succeeds and balance shows unlimited."""
    emp = uuid.uuid4()
    policy_id = await _create_unlimited_policy(async_client, key="adj-unlimited")
    await _assign_employee(async_client, policy_id, employee_id=emp)

    resp = await async_client.post(
        _adjustment_url(),
        json=_adjustment_payload(employee_id=emp, policy_id=policy_id, amount_minutes=480, reason="Grant"),
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201

    bal_resp = await async_client.get(_balances_url(emp), headers=AUTH_HEADERS)
    balance = next(b for b in bal_resp.json()["items"] if b["policy_id"] == policy_id)
    assert balance["is_unlimited"] is True
    assert balance["available_minutes"] is None
    assert balance["accrued_minutes"] == 480


# ---------------------------------------------------------------------------
# Balance invariants
# ---------------------------------------------------------------------------


async def test_invariant_available_equals_accrued_minus_used_minus_held(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Snapshot available = accrued - used - held after adjustments."""
    emp = uuid.uuid4()
    policy_id = await _create_accrual_policy(async_client, key="inv-formula")
    await _assign_employee(async_client, policy_id, employee_id=emp)

    await async_client.post(
        _adjustment_url(),
        json=_adjustment_payload(employee_id=emp, policy_id=policy_id, amount_minutes=960),
        headers=AUTH_HEADERS,
    )

    result = await db_session.execute(
        select(TimeOffBalanceSnapshot).where(
            col(TimeOffBalanceSnapshot.company_id) == COMPANY_ID,
            col(TimeOffBalanceSnapshot.employee_id) == emp,
            col(TimeOffBalanceSnapshot.policy_id) == uuid.UUID(policy_id),
        )
    )
    snapshot = result.scalar_one()
    assert snapshot.available_minutes == snapshot.accrued_minutes - snapshot.used_minutes - snapshot.held_minutes


async def test_invariant_multiple_adjustments_cumulative(async_client: AsyncClient) -> None:
    """Multiple adjustments accumulate correctly: +480, +240, -120 = 600."""
    emp = uuid.uuid4()
    policy_id = await _create_accrual_policy(async_client, key="inv-cumul")
    await _assign_employee(async_client, policy_id, employee_id=emp)

    for amount in [480, 240, -120]:
        await async_client.post(
            _adjustment_url(),
            json=_adjustment_payload(
                employee_id=emp, policy_id=policy_id, amount_minutes=amount, reason=f"adj {amount}"
            ),
            headers=AUTH_HEADERS,
        )

    bal_resp = await async_client.get(_balances_url(emp), headers=AUTH_HEADERS)
    balance = next(b for b in bal_resp.json()["items"] if b["policy_id"] == policy_id)
    assert balance["accrued_minutes"] == 600
    assert balance["available_minutes"] == 600


async def test_invariant_snapshot_matches_ledger_recomputation(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Snapshot values match what recomputing from ledger would produce."""
    from app.services.balance import _compute_balance_from_ledger

    emp = uuid.uuid4()
    policy_id = await _create_accrual_policy(async_client, key="inv-recomp")
    await _assign_employee(async_client, policy_id, employee_id=emp)

    for amount in [480, 240, -120]:
        await async_client.post(
            _adjustment_url(),
            json=_adjustment_payload(employee_id=emp, policy_id=policy_id, amount_minutes=amount),
            headers=AUTH_HEADERS,
        )

    policy_uuid = uuid.UUID(policy_id)
    accrued, used, held = await _compute_balance_from_ledger(db_session, COMPANY_ID, emp, policy_uuid)

    result = await db_session.execute(
        select(TimeOffBalanceSnapshot).where(
            col(TimeOffBalanceSnapshot.company_id) == COMPANY_ID,
            col(TimeOffBalanceSnapshot.employee_id) == emp,
            col(TimeOffBalanceSnapshot.policy_id) == policy_uuid,
        )
    )
    snapshot = result.scalar_one()
    assert snapshot.accrued_minutes == accrued
    assert snapshot.used_minutes == used
    assert snapshot.held_minutes == held
    assert snapshot.available_minutes == accrued - used - held


async def test_invariant_snapshot_version_increments(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Each adjustment increments the snapshot version by 1."""
    emp = uuid.uuid4()
    policy_id = await _create_accrual_policy(async_client, key="inv-ver")
    await _assign_employee(async_client, policy_id, employee_id=emp)

    for i in range(3):
        await async_client.post(
            _adjustment_url(),
            json=_adjustment_payload(employee_id=emp, policy_id=policy_id, amount_minutes=100 * (i + 1)),
            headers=AUTH_HEADERS,
        )

    result = await db_session.execute(
        select(TimeOffBalanceSnapshot).where(
            col(TimeOffBalanceSnapshot.company_id) == COMPANY_ID,
            col(TimeOffBalanceSnapshot.employee_id) == emp,
            col(TimeOffBalanceSnapshot.policy_id) == uuid.UUID(policy_id),
        )
    )
    snapshot = result.scalar_one()
    # Initial creation (version 1) + 3 adjustments = version 4.
    assert snapshot.version == 4


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------


async def test_adjustment_creates_audit_entry(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Adjustment writes an audit log entry."""
    emp = uuid.uuid4()
    policy_id = await _create_accrual_policy(async_client, key="aud-create")
    await _assign_employee(async_client, policy_id, employee_id=emp)

    adj_resp = await async_client.post(
        _adjustment_url(),
        json=_adjustment_payload(employee_id=emp, policy_id=policy_id, amount_minutes=480, reason="Audit test"),
        headers=AUTH_HEADERS,
    )
    entry_id = adj_resp.json()["id"]

    result = await db_session.execute(
        select(AuditLog).where(
            col(AuditLog.company_id) == COMPANY_ID,
            col(AuditLog.entity_type) == "ADJUSTMENT",
            col(AuditLog.action) == "CREATE",
        )
    )
    entries = list(result.scalars().all())
    audit_entries = [e for e in entries if str(e.entity_id) == entry_id]
    assert len(audit_entries) >= 1

    audit = audit_entries[0]
    assert audit.before_json is None
    assert audit.after_json is not None
    assert audit.after_json["amount_minutes"] == 480


async def test_adjustment_audit_contains_reason(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Audit after_json includes the adjustment reason in metadata."""
    emp = uuid.uuid4()
    policy_id = await _create_accrual_policy(async_client, key="aud-reason")
    await _assign_employee(async_client, policy_id, employee_id=emp)

    adj_resp = await async_client.post(
        _adjustment_url(),
        json=_adjustment_payload(employee_id=emp, policy_id=policy_id, reason="Specific reason"),
        headers=AUTH_HEADERS,
    )
    entry_id = adj_resp.json()["id"]

    result = await db_session.execute(
        select(AuditLog).where(
            col(AuditLog.entity_type) == "ADJUSTMENT",
            col(AuditLog.action) == "CREATE",
        )
    )
    entries = list(result.scalars().all())
    audit = next(e for e in entries if str(e.entity_id) == entry_id)
    assert audit.after_json is not None
    assert audit.after_json["metadata_json"]["reason"] == "Specific reason"


async def test_adjustment_audit_actor_matches_auth_user(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Audit actor_id matches the authenticated admin user."""
    custom_user = uuid.uuid4()
    custom_headers = {
        "X-Company-Id": str(COMPANY_ID),
        "X-User-Id": str(custom_user),
        "X-Role": "admin",
    }
    emp = uuid.uuid4()
    policy_id = await _create_accrual_policy(async_client, key="aud-actor")
    await _assign_employee(async_client, policy_id, employee_id=emp)

    await async_client.post(
        _adjustment_url(),
        json=_adjustment_payload(employee_id=emp, policy_id=policy_id),
        headers=custom_headers,
    )

    result = await db_session.execute(
        select(AuditLog).where(
            col(AuditLog.entity_type) == "ADJUSTMENT",
            col(AuditLog.actor_id) == custom_user,
        )
    )
    entries = list(result.scalars().all())
    assert len(entries) >= 1
    for entry in entries:
        assert entry.actor_id == custom_user


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


async def test_create_adjustment_zero_amount(async_client: AsyncClient) -> None:
    """Zero-amount adjustment is allowed (creates a ledger entry with no balance impact)."""
    emp = uuid.uuid4()
    policy_id = await _create_accrual_policy(async_client, key="adj-zero")
    await _assign_employee(async_client, policy_id, employee_id=emp)

    resp = await async_client.post(
        _adjustment_url(),
        json=_adjustment_payload(employee_id=emp, policy_id=policy_id, amount_minutes=0, reason="No-op note"),
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201
    assert resp.json()["amount_minutes"] == 0


async def test_snapshot_created_on_first_adjustment(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Snapshot is created atomically when none exists prior to adjustment."""
    emp = uuid.uuid4()
    policy_id = await _create_accrual_policy(async_client, key="snap-first")
    await _assign_employee(async_client, policy_id, employee_id=emp)

    # Verify no snapshot yet.
    result = await db_session.execute(
        select(TimeOffBalanceSnapshot).where(
            col(TimeOffBalanceSnapshot.company_id) == COMPANY_ID,
            col(TimeOffBalanceSnapshot.employee_id) == emp,
            col(TimeOffBalanceSnapshot.policy_id) == uuid.UUID(policy_id),
        )
    )
    assert result.scalar_one_or_none() is None

    # Create adjustment.
    await async_client.post(
        _adjustment_url(),
        json=_adjustment_payload(employee_id=emp, policy_id=policy_id, amount_minutes=480),
        headers=AUTH_HEADERS,
    )

    # Now snapshot should exist.
    result = await db_session.execute(
        select(TimeOffBalanceSnapshot).where(
            col(TimeOffBalanceSnapshot.company_id) == COMPANY_ID,
            col(TimeOffBalanceSnapshot.employee_id) == emp,
            col(TimeOffBalanceSnapshot.policy_id) == uuid.UUID(policy_id),
        )
    )
    snapshot = result.scalar_one()
    assert snapshot.accrued_minutes == 480
    assert snapshot.available_minutes == 480


# ---------------------------------------------------------------------------
# Service-layer tests (direct function calls with db_session)
# ---------------------------------------------------------------------------


async def test_compute_balance_from_ledger_empty(db_session: AsyncSession) -> None:
    """No ledger entries returns (0, 0, 0)."""
    from app.services.balance import _compute_balance_from_ledger

    accrued, used, held = await _compute_balance_from_ledger(db_session, uuid.uuid4(), uuid.uuid4(), uuid.uuid4())
    assert accrued == 0
    assert used == 0
    assert held == 0


async def test_compute_balance_from_ledger_mixed_entries(db_session: AsyncSession) -> None:
    """Mixed entry types compute correctly."""
    from app.services.balance import _compute_balance_from_ledger

    company_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    policy_id = uuid.uuid4()
    version_id = uuid.uuid4()

    # Create the required policy and version for FK constraints.
    policy = TimeOffPolicy(id=policy_id, company_id=company_id, key="compute-test", category="VACATION")
    db_session.add(policy)
    await db_session.flush()

    version = TimeOffPolicyVersion(
        id=version_id,
        policy_id=policy_id,
        version=1,
        effective_from=date(2025, 1, 1),
        type="ACCRUAL",
        accrual_method="TIME",
        settings_json={
            "type": "ACCRUAL",
            "accrual_method": "TIME",
            "accrual_frequency": "MONTHLY",
            "rate_minutes_per_month": 480,
        },
        created_by=uuid.uuid4(),
    )
    db_session.add(version)
    await db_session.flush()

    # Insert mixed ledger entries.
    entries = [
        (LedgerEntryType.ACCRUAL, 480, "accrual-1"),
        (LedgerEntryType.ACCRUAL, 480, "accrual-2"),
        (LedgerEntryType.ADJUSTMENT, 120, "adj-1"),
        (LedgerEntryType.ADJUSTMENT, -60, "adj-2"),
        (LedgerEntryType.HOLD, -240, "hold-1"),
        (LedgerEntryType.HOLD_RELEASE, 240, "release-1"),
        (LedgerEntryType.HOLD, -120, "hold-2"),
        (LedgerEntryType.USAGE, -360, "usage-1"),
    ]

    for entry_type, amount, source_id in entries:
        entry = TimeOffLedgerEntry(
            company_id=company_id,
            employee_id=employee_id,
            policy_id=policy_id,
            policy_version_id=version_id,
            entry_type=entry_type.value,
            amount_minutes=amount,
            effective_at=datetime.now(UTC),
            source_type=LedgerSourceType.SYSTEM.value,
            source_id=source_id,
        )
        db_session.add(entry)

    await db_session.flush()

    accrued, used, held = await _compute_balance_from_ledger(db_session, company_id, employee_id, policy_id)

    # accrued = 480 + 480 + 120 + (-60) = 1020
    assert accrued == 1020
    # used = abs(-360) = 360
    assert used == 360
    # held = abs(-240) - abs(240) + abs(-120) = 240 - 240 + 120 = 120
    assert held == 120


async def test_get_or_create_snapshot_creates_new(db_session: AsyncSession) -> None:
    """Snapshot is created when none exists."""
    from app.services.balance import _get_or_create_snapshot_for_update

    company_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    policy_id = uuid.uuid4()

    # Create the required policy for FK constraint.
    policy = TimeOffPolicy(id=policy_id, company_id=company_id, key="snap-new", category="VACATION")
    db_session.add(policy)
    await db_session.flush()

    snapshot = await _get_or_create_snapshot_for_update(db_session, company_id, employee_id, policy_id)
    assert snapshot.company_id == company_id
    assert snapshot.employee_id == employee_id
    assert snapshot.policy_id == policy_id
    assert snapshot.accrued_minutes == 0
    assert snapshot.available_minutes == 0
    assert snapshot.version == 1


async def test_get_or_create_snapshot_returns_existing(db_session: AsyncSession) -> None:
    """Existing snapshot is returned."""
    from app.services.balance import _get_or_create_snapshot_for_update

    company_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    policy_id = uuid.uuid4()

    # Create the required policy for FK constraint.
    policy = TimeOffPolicy(id=policy_id, company_id=company_id, key="snap-exist", category="VACATION")
    db_session.add(policy)
    await db_session.flush()

    # Pre-create a snapshot.
    existing = TimeOffBalanceSnapshot(
        company_id=company_id,
        employee_id=employee_id,
        policy_id=policy_id,
        accrued_minutes=500,
        used_minutes=100,
        held_minutes=50,
        available_minutes=350,
        version=3,
    )
    db_session.add(existing)
    await db_session.flush()

    snapshot = await _get_or_create_snapshot_for_update(db_session, company_id, employee_id, policy_id)
    assert snapshot.accrued_minutes == 500
    assert snapshot.version == 3
