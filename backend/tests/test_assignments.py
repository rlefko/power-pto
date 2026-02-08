"""Integration tests for assignment CRUD, effective dating, overlap detection, and audit."""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select
from sqlmodel import col

from app.exceptions import AppError
from app.models.assignment import TimeOffPolicyAssignment
from app.models.audit import AuditLog
from app.services import assignment as assignment_service

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


async def _create_policy(client: AsyncClient, key: str = "vacation-ft") -> str:
    """Create a policy and return its ID."""
    resp = await client.post(
        POLICIES_URL,
        json={
            "key": key,
            "category": "VACATION",
            "version": {
                "effective_from": "2025-01-01",
                "settings": {"type": "UNLIMITED"},
            },
        },
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201
    policy_id: str = resp.json()["id"]
    return policy_id


def _assignments_url(policy_id: str) -> str:
    """Build the policy-scoped assignments URL."""
    return f"/companies/{COMPANY_ID}/policies/{policy_id}/assignments"


def _company_assignment_url(assignment_id: str) -> str:
    """Build the company-scoped assignment URL for DELETE."""
    return f"/companies/{COMPANY_ID}/assignments/{assignment_id}"


def _employee_assignments_url(employee_id: uuid.UUID | str = EMPLOYEE_ID) -> str:
    """Build the employee-scoped assignments URL."""
    return f"/companies/{COMPANY_ID}/employees/{employee_id}/assignments"


def _assignment_payload(
    employee_id: uuid.UUID = EMPLOYEE_ID,
    effective_from: str = "2025-01-01",
    effective_to: str | None = None,
) -> dict:  # type: ignore[type-arg]
    payload: dict = {  # type: ignore[type-arg]
        "employee_id": str(employee_id),
        "effective_from": effective_from,
    }
    if effective_to is not None:
        payload["effective_to"] = effective_to
    return payload


# ---------------------------------------------------------------------------
# Create assignment tests
# ---------------------------------------------------------------------------


async def test_create_assignment(async_client: AsyncClient) -> None:
    policy_id = await _create_policy(async_client)
    url = _assignments_url(policy_id)

    resp = await async_client.post(url, json=_assignment_payload(), headers=AUTH_HEADERS)
    assert resp.status_code == 201
    data = resp.json()
    assert data["company_id"] == str(COMPANY_ID)
    assert data["employee_id"] == str(EMPLOYEE_ID)
    assert data["policy_id"] == policy_id
    assert data["effective_from"] == "2025-01-01"
    assert data["effective_to"] is None
    assert data["created_by"] == str(USER_ID)
    assert data["id"] is not None
    assert data["created_at"] is not None


async def test_create_assignment_with_effective_to(async_client: AsyncClient) -> None:
    policy_id = await _create_policy(async_client)
    url = _assignments_url(policy_id)

    resp = await async_client.post(
        url,
        json=_assignment_payload(effective_from="2025-01-01", effective_to="2025-12-31"),
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["effective_from"] == "2025-01-01"
    assert data["effective_to"] == "2025-12-31"


async def test_create_assignment_policy_not_found(async_client: AsyncClient) -> None:
    fake_policy_id = str(uuid.uuid4())
    url = _assignments_url(fake_policy_id)
    resp = await async_client.post(url, json=_assignment_payload(), headers=AUTH_HEADERS)
    assert resp.status_code == 404


async def test_create_assignment_wrong_company(async_client: AsyncClient) -> None:
    policy_id = await _create_policy(async_client)
    other_company = uuid.uuid4()
    url = f"/companies/{other_company}/policies/{policy_id}/assignments"
    wrong_headers = {
        "X-Company-Id": str(other_company),
        "X-User-Id": str(USER_ID),
        "X-Role": "admin",
    }
    resp = await async_client.post(url, json=_assignment_payload(), headers=wrong_headers)
    assert resp.status_code == 404


async def test_create_assignment_missing_fields(async_client: AsyncClient) -> None:
    policy_id = await _create_policy(async_client)
    url = _assignments_url(policy_id)
    resp = await async_client.post(url, json={"employee_id": str(uuid.uuid4())}, headers=AUTH_HEADERS)
    assert resp.status_code == 422


async def test_create_assignment_effective_to_before_from(async_client: AsyncClient) -> None:
    policy_id = await _create_policy(async_client)
    url = _assignments_url(policy_id)
    resp = await async_client.post(
        url,
        json=_assignment_payload(effective_from="2025-06-01", effective_to="2025-01-01"),
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 422


async def test_create_assignment_duplicate_same_effective_from(async_client: AsyncClient) -> None:
    policy_id = await _create_policy(async_client)
    url = _assignments_url(policy_id)
    payload = _assignment_payload()

    resp1 = await async_client.post(url, json=payload, headers=AUTH_HEADERS)
    assert resp1.status_code == 201

    resp2 = await async_client.post(url, json=payload, headers=AUTH_HEADERS)
    assert resp2.status_code == 409


async def test_create_assignment_overlapping_open_ended(async_client: AsyncClient) -> None:
    """An open-ended assignment blocks any new assignment for the same employee/policy."""
    policy_id = await _create_policy(async_client)
    url = _assignments_url(policy_id)

    resp1 = await async_client.post(url, json=_assignment_payload(effective_from="2025-01-01"), headers=AUTH_HEADERS)
    assert resp1.status_code == 201

    resp2 = await async_client.post(url, json=_assignment_payload(effective_from="2025-06-01"), headers=AUTH_HEADERS)
    assert resp2.status_code == 409


async def test_create_assignment_overlapping_bounded(async_client: AsyncClient) -> None:
    """Bounded assignments that overlap should be rejected."""
    policy_id = await _create_policy(async_client)
    url = _assignments_url(policy_id)

    resp1 = await async_client.post(
        url,
        json=_assignment_payload(effective_from="2025-01-01", effective_to="2025-06-01"),
        headers=AUTH_HEADERS,
    )
    assert resp1.status_code == 201

    # Overlapping: starts during the existing assignment
    resp2 = await async_client.post(
        url,
        json=_assignment_payload(effective_from="2025-03-01", effective_to="2025-09-01"),
        headers=AUTH_HEADERS,
    )
    assert resp2.status_code == 409


async def test_create_assignment_adjacent_no_overlap(async_client: AsyncClient) -> None:
    """Adjacent assignments (one ends where the next starts) should be allowed."""
    policy_id = await _create_policy(async_client)
    url = _assignments_url(policy_id)

    resp1 = await async_client.post(
        url,
        json=_assignment_payload(effective_from="2025-01-01", effective_to="2025-06-01"),
        headers=AUTH_HEADERS,
    )
    assert resp1.status_code == 201

    resp2 = await async_client.post(
        url,
        json=_assignment_payload(effective_from="2025-06-01", effective_to="2025-12-01"),
        headers=AUTH_HEADERS,
    )
    assert resp2.status_code == 201


async def test_create_assignment_different_policies_same_employee(async_client: AsyncClient) -> None:
    """Same employee can be assigned to different policies."""
    policy_id_1 = await _create_policy(async_client, key="vacation")
    policy_id_2 = await _create_policy(async_client, key="sick")

    resp1 = await async_client.post(_assignments_url(policy_id_1), json=_assignment_payload(), headers=AUTH_HEADERS)
    assert resp1.status_code == 201

    resp2 = await async_client.post(_assignments_url(policy_id_2), json=_assignment_payload(), headers=AUTH_HEADERS)
    assert resp2.status_code == 201


async def test_create_assignment_different_employees_same_policy(async_client: AsyncClient) -> None:
    """Different employees can be assigned to the same policy."""
    policy_id = await _create_policy(async_client)
    url = _assignments_url(policy_id)

    emp1 = uuid.uuid4()
    emp2 = uuid.uuid4()

    resp1 = await async_client.post(url, json=_assignment_payload(employee_id=emp1), headers=AUTH_HEADERS)
    assert resp1.status_code == 201

    resp2 = await async_client.post(url, json=_assignment_payload(employee_id=emp2), headers=AUTH_HEADERS)
    assert resp2.status_code == 201


async def test_non_admin_cannot_create_assignment(async_client: AsyncClient) -> None:
    policy_id = await _create_policy(async_client)
    url = _assignments_url(policy_id)
    resp = await async_client.post(url, json=_assignment_payload(), headers=EMPLOYEE_HEADERS)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# List by policy tests
# ---------------------------------------------------------------------------


async def test_list_assignments_by_policy_empty(async_client: AsyncClient) -> None:
    policy_id = await _create_policy(async_client)
    resp = await async_client.get(_assignments_url(policy_id), headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_list_assignments_by_policy_returns_created(async_client: AsyncClient) -> None:
    policy_id = await _create_policy(async_client)
    url = _assignments_url(policy_id)

    emp1 = uuid.uuid4()
    emp2 = uuid.uuid4()
    await async_client.post(url, json=_assignment_payload(employee_id=emp1), headers=AUTH_HEADERS)
    await async_client.post(url, json=_assignment_payload(employee_id=emp2), headers=AUTH_HEADERS)

    resp = await async_client.get(url, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


async def test_list_assignments_by_policy_pagination(async_client: AsyncClient) -> None:
    policy_id = await _create_policy(async_client)
    url = _assignments_url(policy_id)

    for _ in range(3):
        emp = uuid.uuid4()
        await async_client.post(url, json=_assignment_payload(employee_id=emp), headers=AUTH_HEADERS)

    resp = await async_client.get(f"{url}?offset=0&limit=2", headers=AUTH_HEADERS)
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2

    resp2 = await async_client.get(f"{url}?offset=2&limit=2", headers=AUTH_HEADERS)
    data2 = resp2.json()
    assert len(data2["items"]) == 1


async def test_list_assignments_by_policy_not_found(async_client: AsyncClient) -> None:
    fake_id = uuid.uuid4()
    resp = await async_client.get(_assignments_url(str(fake_id)), headers=AUTH_HEADERS)
    assert resp.status_code == 404


async def test_list_assignments_by_policy_company_isolation(async_client: AsyncClient) -> None:
    policy_id = await _create_policy(async_client)
    url = _assignments_url(policy_id)
    await async_client.post(url, json=_assignment_payload(), headers=AUTH_HEADERS)

    # Different company should not see assignments
    other_company = uuid.uuid4()
    other_headers = {
        "X-Company-Id": str(other_company),
        "X-User-Id": str(USER_ID),
        "X-Role": "admin",
    }
    # Create a separate policy in the other company
    other_policy_resp = await async_client.post(
        f"/companies/{other_company}/policies",
        json={
            "key": "vacation-ft",
            "category": "VACATION",
            "version": {"effective_from": "2025-01-01", "settings": {"type": "UNLIMITED"}},
        },
        headers=other_headers,
    )
    other_policy_id = other_policy_resp.json()["id"]
    resp = await async_client.get(
        f"/companies/{other_company}/policies/{other_policy_id}/assignments",
        headers=other_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


async def test_employee_can_list_assignments_by_policy(async_client: AsyncClient) -> None:
    policy_id = await _create_policy(async_client)
    resp = await async_client.get(_assignments_url(policy_id), headers=EMPLOYEE_HEADERS)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# List by employee tests
# ---------------------------------------------------------------------------


async def test_list_assignments_by_employee_empty(async_client: AsyncClient) -> None:
    resp = await async_client.get(_employee_assignments_url(uuid.uuid4()), headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_list_assignments_by_employee_returns_created(async_client: AsyncClient) -> None:
    policy_id_1 = await _create_policy(async_client, key="vacation")
    policy_id_2 = await _create_policy(async_client, key="sick")

    emp = uuid.uuid4()
    await async_client.post(
        _assignments_url(policy_id_1), json=_assignment_payload(employee_id=emp), headers=AUTH_HEADERS
    )
    await async_client.post(
        _assignments_url(policy_id_2), json=_assignment_payload(employee_id=emp), headers=AUTH_HEADERS
    )

    resp = await async_client.get(_employee_assignments_url(emp), headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


async def test_list_assignments_by_employee_pagination(async_client: AsyncClient) -> None:
    emp = uuid.uuid4()
    for i in range(3):
        pid = await _create_policy(async_client, key=f"policy-{i}")
        await async_client.post(_assignments_url(pid), json=_assignment_payload(employee_id=emp), headers=AUTH_HEADERS)

    url = _employee_assignments_url(emp)
    resp = await async_client.get(f"{url}?offset=0&limit=2", headers=AUTH_HEADERS)
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2

    resp2 = await async_client.get(f"{url}?offset=2&limit=2", headers=AUTH_HEADERS)
    data2 = resp2.json()
    assert len(data2["items"]) == 1


async def test_list_assignments_by_employee_company_isolation(async_client: AsyncClient) -> None:
    policy_id = await _create_policy(async_client)
    emp = uuid.uuid4()
    await async_client.post(
        _assignments_url(policy_id), json=_assignment_payload(employee_id=emp), headers=AUTH_HEADERS
    )

    other_company = uuid.uuid4()
    other_headers = {
        "X-Company-Id": str(other_company),
        "X-User-Id": str(USER_ID),
        "X-Role": "admin",
    }
    resp = await async_client.get(
        f"/companies/{other_company}/employees/{emp}/assignments",
        headers=other_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# End-date assignment tests
# ---------------------------------------------------------------------------


async def test_end_date_assignment(async_client: AsyncClient) -> None:
    policy_id = await _create_policy(async_client)
    create_resp = await async_client.post(_assignments_url(policy_id), json=_assignment_payload(), headers=AUTH_HEADERS)
    assert create_resp.status_code == 201
    assignment_id = create_resp.json()["id"]

    resp = await async_client.delete(
        f"{_company_assignment_url(assignment_id)}?effective_to=2025-06-01",
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["effective_to"] == "2025-06-01"
    assert data["id"] == assignment_id


async def test_end_date_assignment_not_found(async_client: AsyncClient) -> None:
    fake_id = str(uuid.uuid4())
    resp = await async_client.delete(
        f"{_company_assignment_url(fake_id)}?effective_to=2025-06-01",
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 404


async def test_end_date_assignment_already_ended(async_client: AsyncClient) -> None:
    policy_id = await _create_policy(async_client)
    create_resp = await async_client.post(
        _assignments_url(policy_id),
        json=_assignment_payload(effective_from="2025-01-01", effective_to="2025-06-01"),
        headers=AUTH_HEADERS,
    )
    assignment_id = create_resp.json()["id"]

    resp = await async_client.delete(
        f"{_company_assignment_url(assignment_id)}?effective_to=2025-12-01",
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 400


async def test_end_date_assignment_effective_to_before_from(async_client: AsyncClient) -> None:
    policy_id = await _create_policy(async_client)
    create_resp = await async_client.post(
        _assignments_url(policy_id),
        json=_assignment_payload(effective_from="2025-06-01"),
        headers=AUTH_HEADERS,
    )
    assignment_id = create_resp.json()["id"]

    resp = await async_client.delete(
        f"{_company_assignment_url(assignment_id)}?effective_to=2025-01-01",
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 400


async def test_non_admin_cannot_end_date_assignment(async_client: AsyncClient) -> None:
    policy_id = await _create_policy(async_client)
    create_resp = await async_client.post(_assignments_url(policy_id), json=_assignment_payload(), headers=AUTH_HEADERS)
    assignment_id = create_resp.json()["id"]

    resp = await async_client.delete(
        f"{_company_assignment_url(assignment_id)}?effective_to=2025-06-01",
        headers=EMPLOYEE_HEADERS,
    )
    assert resp.status_code == 403


async def test_end_date_assignment_wrong_company(async_client: AsyncClient) -> None:
    policy_id = await _create_policy(async_client)
    create_resp = await async_client.post(_assignments_url(policy_id), json=_assignment_payload(), headers=AUTH_HEADERS)
    assignment_id = create_resp.json()["id"]

    other_company = uuid.uuid4()
    wrong_headers = {
        "X-Company-Id": str(other_company),
        "X-User-Id": str(USER_ID),
        "X-Role": "admin",
    }
    resp = await async_client.delete(
        f"/companies/{other_company}/assignments/{assignment_id}?effective_to=2025-06-01",
        headers=wrong_headers,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Audit tests
# ---------------------------------------------------------------------------


async def test_create_assignment_writes_audit_entry(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    policy_id = await _create_policy(async_client)
    resp = await async_client.post(_assignments_url(policy_id), json=_assignment_payload(), headers=AUTH_HEADERS)
    assert resp.status_code == 201
    assignment_id = resp.json()["id"]

    result = await db_session.execute(
        select(AuditLog).where(
            col(AuditLog.company_id) == COMPANY_ID,
            col(AuditLog.entity_type) == "ASSIGNMENT",
            col(AuditLog.action) == "CREATE",
        )
    )
    entries = list(result.scalars().all())
    assignment_entries = [e for e in entries if str(e.entity_id) == assignment_id]
    assert len(assignment_entries) >= 1

    entry = assignment_entries[0]
    assert str(entry.actor_id) == str(USER_ID)
    assert entry.before_json is None
    assert entry.after_json is not None
    assert entry.after_json["employee_id"] == str(EMPLOYEE_ID)
    assert entry.after_json["policy_id"] == policy_id


async def test_end_date_assignment_writes_audit_entry(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    policy_id = await _create_policy(async_client)
    create_resp = await async_client.post(_assignments_url(policy_id), json=_assignment_payload(), headers=AUTH_HEADERS)
    assignment_id = create_resp.json()["id"]

    await async_client.delete(
        f"{_company_assignment_url(assignment_id)}?effective_to=2025-06-01",
        headers=AUTH_HEADERS,
    )

    result = await db_session.execute(
        select(AuditLog).where(
            col(AuditLog.company_id) == COMPANY_ID,
            col(AuditLog.entity_type) == "ASSIGNMENT",
            col(AuditLog.action) == "UPDATE",
        )
    )
    entries = list(result.scalars().all())
    update_entries = [e for e in entries if str(e.entity_id) == assignment_id]
    assert len(update_entries) >= 1

    entry = update_entries[0]
    assert entry.before_json is not None
    assert entry.after_json is not None
    assert entry.before_json["effective_to"] is None
    assert entry.after_json["effective_to"] == "2025-06-01"


async def test_audit_actor_matches_auth_user_assignments(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    custom_user = uuid.uuid4()
    custom_headers = {
        "X-Company-Id": str(COMPANY_ID),
        "X-User-Id": str(custom_user),
        "X-Role": "admin",
    }
    policy_id = await _create_policy(async_client)
    resp = await async_client.post(_assignments_url(policy_id), json=_assignment_payload(), headers=custom_headers)
    assert resp.status_code == 201

    result = await db_session.execute(
        select(AuditLog).where(
            col(AuditLog.company_id) == COMPANY_ID,
            col(AuditLog.entity_type) == "ASSIGNMENT",
            col(AuditLog.actor_id) == custom_user,
        )
    )
    entries = list(result.scalars().all())
    assert len(entries) >= 1
    for entry in entries:
        assert entry.actor_id == custom_user


# ---------------------------------------------------------------------------
# verify_active_assignment tests
# ---------------------------------------------------------------------------


async def test_verify_active_assignment_found(db_session: AsyncSession) -> None:
    """Active open-ended assignment is found."""
    company_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    policy_id = uuid.uuid4()

    # Create the policy first (needed for FK)
    from app.models.policy import TimeOffPolicy

    policy = TimeOffPolicy(id=policy_id, company_id=company_id, key="test-policy", category="VACATION")
    db_session.add(policy)
    await db_session.flush()

    assignment = TimeOffPolicyAssignment(
        company_id=company_id,
        employee_id=employee_id,
        policy_id=policy_id,
        effective_from=date(2025, 1, 1),
        effective_to=None,
        created_by=uuid.uuid4(),
    )
    db_session.add(assignment)
    await db_session.flush()

    result = await assignment_service.verify_active_assignment(
        db_session, company_id, employee_id, policy_id, date(2025, 6, 15)
    )
    assert result.id == assignment.id


async def test_verify_active_assignment_not_found_no_assignment(db_session: AsyncSession) -> None:
    """No assignment at all raises error."""
    with pytest.raises(AppError, match="Employee is not assigned to this policy"):
        await assignment_service.verify_active_assignment(
            db_session, uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), date(2025, 6, 15)
        )


async def test_verify_active_assignment_not_found_before_start(db_session: AsyncSession) -> None:
    """Date before effective_from raises error."""
    company_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    policy_id = uuid.uuid4()

    from app.models.policy import TimeOffPolicy

    policy = TimeOffPolicy(id=policy_id, company_id=company_id, key="test-policy-2", category="VACATION")
    db_session.add(policy)
    await db_session.flush()

    assignment = TimeOffPolicyAssignment(
        company_id=company_id,
        employee_id=employee_id,
        policy_id=policy_id,
        effective_from=date(2025, 6, 1),
        effective_to=None,
        created_by=uuid.uuid4(),
    )
    db_session.add(assignment)
    await db_session.flush()

    with pytest.raises(AppError, match="Employee is not assigned to this policy"):
        await assignment_service.verify_active_assignment(
            db_session, company_id, employee_id, policy_id, date(2025, 5, 15)
        )


async def test_verify_active_assignment_not_found_after_end(db_session: AsyncSession) -> None:
    """Date on or after effective_to raises error (half-open interval)."""
    company_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    policy_id = uuid.uuid4()

    from app.models.policy import TimeOffPolicy

    policy = TimeOffPolicy(id=policy_id, company_id=company_id, key="test-policy-3", category="VACATION")
    db_session.add(policy)
    await db_session.flush()

    assignment = TimeOffPolicyAssignment(
        company_id=company_id,
        employee_id=employee_id,
        policy_id=policy_id,
        effective_from=date(2025, 1, 1),
        effective_to=date(2025, 6, 1),
        created_by=uuid.uuid4(),
    )
    db_session.add(assignment)
    await db_session.flush()

    # Exactly on the effective_to date (exclusive) should fail
    with pytest.raises(AppError, match="Employee is not assigned to this policy"):
        await assignment_service.verify_active_assignment(
            db_session, company_id, employee_id, policy_id, date(2025, 6, 1)
        )

    # After effective_to should also fail
    with pytest.raises(AppError, match="Employee is not assigned to this policy"):
        await assignment_service.verify_active_assignment(
            db_session, company_id, employee_id, policy_id, date(2025, 7, 1)
        )


async def test_verify_active_assignment_on_effective_from(db_session: AsyncSession) -> None:
    """Date exactly on effective_from should succeed (inclusive)."""
    company_id = uuid.uuid4()
    employee_id = uuid.uuid4()
    policy_id = uuid.uuid4()

    from app.models.policy import TimeOffPolicy

    policy = TimeOffPolicy(id=policy_id, company_id=company_id, key="test-policy-4", category="VACATION")
    db_session.add(policy)
    await db_session.flush()

    assignment = TimeOffPolicyAssignment(
        company_id=company_id,
        employee_id=employee_id,
        policy_id=policy_id,
        effective_from=date(2025, 1, 1),
        effective_to=date(2025, 12, 31),
        created_by=uuid.uuid4(),
    )
    db_session.add(assignment)
    await db_session.flush()

    result = await assignment_service.verify_active_assignment(
        db_session, company_id, employee_id, policy_id, date(2025, 1, 1)
    )
    assert result.id == assignment.id
