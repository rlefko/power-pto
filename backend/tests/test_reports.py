"""Comprehensive tests for reporting/audit endpoints: audit log queries,
balance summaries, and ledger exports.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

import pytest

from app.services.employee import EmployeeInfo, InMemoryEmployeeService, set_employee_service

if TYPE_CHECKING:
    from collections.abc import Iterator

    from httpx import AsyncClient

COMPANY_ID = uuid.uuid4()
OTHER_COMPANY_ID = uuid.uuid4()
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
AUDIT_URL = f"/companies/{COMPANY_ID}/audit-log"
BALANCES_URL = f"/companies/{COMPANY_ID}/reports/balances"
LEDGER_URL = f"/companies/{COMPANY_ID}/reports/ledger"


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
# Test helpers
# ---------------------------------------------------------------------------


async def _create_policy(client: AsyncClient, key: str = "vacation") -> str:
    """Create an unlimited policy and return its ID (generates audit entries)."""
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


async def _setup_accrual_with_balance(client: AsyncClient) -> str:
    """Create an accrual policy, assign employee, trigger accrual, return policy ID."""
    resp = await client.post(
        POLICIES_URL,
        json={
            "key": "vacation-accrual",
            "category": "VACATION",
            "version": {
                "effective_from": "2025-01-01",
                "settings": {
                    "type": "ACCRUAL",
                    "accrual_method": "TIME",
                    "accrual_frequency": "DAILY",
                    "accrual_timing": "START_OF_PERIOD",
                    "rate_minutes_per_day": 40,
                },
            },
        },
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201
    pid: str = resp.json()["id"]

    # Assign employee
    assign_resp = await client.post(
        f"{POLICIES_URL}/{pid}/assignments",
        json={"employee_id": str(EMPLOYEE_ID), "effective_from": "2025-01-01"},
        headers=AUTH_HEADERS,
    )
    assert assign_resp.status_code == 201

    # Trigger accrual
    trigger_url = f"/companies/{COMPANY_ID}/accruals/trigger"
    trigger_resp = await client.post(
        trigger_url,
        params={"target_date": "2025-01-01"},
        headers=AUTH_HEADERS,
    )
    assert trigger_resp.status_code == 200

    return pid


# ===========================================================================
# Audit log tests
# ===========================================================================


class TestAuditLog:
    """Tests for the audit log query endpoint."""

    async def test_audit_log_empty(self, async_client: AsyncClient) -> None:
        """No mutations yet returns empty audit log list."""
        resp = await async_client.get(AUDIT_URL, headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_audit_log_after_policy_create(self, async_client: AsyncClient) -> None:
        """Creating a policy generates audit entries that appear in the audit log."""
        await _create_policy(async_client, key="audit-policy-1")

        resp = await async_client.get(AUDIT_URL, headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] > 0
        assert len(data["items"]) > 0

        # Verify structure of audit log entries
        entry = data["items"][0]
        assert "id" in entry
        assert "company_id" in entry
        assert "actor_id" in entry
        assert "entity_type" in entry
        assert "entity_id" in entry
        assert "action" in entry
        assert "created_at" in entry

    async def test_audit_log_filter_entity_type(self, async_client: AsyncClient) -> None:
        """Filter audit log by entity_type=POLICY returns only policy entries."""
        await _create_policy(async_client, key="audit-filter-type-1")

        resp = await async_client.get(
            AUDIT_URL,
            params={"entity_type": "POLICY"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        for entry in data["items"]:
            assert entry["entity_type"] == "POLICY"

    async def test_audit_log_filter_action(self, async_client: AsyncClient) -> None:
        """Filter audit log by action=CREATE returns only CREATE entries."""
        await _create_policy(async_client, key="audit-filter-action-1")

        resp = await async_client.get(
            AUDIT_URL,
            params={"action": "CREATE"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        for entry in data["items"]:
            assert entry["action"] == "CREATE"

    async def test_audit_log_pagination(self, async_client: AsyncClient) -> None:
        """Create multiple policies to generate audit entries, then test offset/limit."""
        for i in range(4):
            await _create_policy(async_client, key=f"audit-page-{i}")

        # Get first page
        resp1 = await async_client.get(
            AUDIT_URL,
            params={"offset": 0, "limit": 2},
            headers=AUTH_HEADERS,
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["total"] >= 4
        assert len(data1["items"]) == 2

        # Get second page
        resp2 = await async_client.get(
            AUDIT_URL,
            params={"offset": 2, "limit": 2},
            headers=AUTH_HEADERS,
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert len(data2["items"]) >= 1

        # Ensure pages return different entries
        page1_ids = {e["id"] for e in data1["items"]}
        page2_ids = {e["id"] for e in data2["items"]}
        assert page1_ids.isdisjoint(page2_ids)

    async def test_audit_log_admin_only(self, async_client: AsyncClient) -> None:
        """Employee role gets 403 when querying audit log."""
        resp = await async_client.get(AUDIT_URL, headers=EMPLOYEE_HEADERS)
        assert resp.status_code == 403


# ===========================================================================
# Balance summary tests
# ===========================================================================


class TestBalanceSummary:
    """Tests for the company balance summary endpoint."""

    async def test_balance_summary_empty(self, async_client: AsyncClient) -> None:
        """No assignments returns empty balance summary."""
        resp = await async_client.get(BALANCES_URL, headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_balance_summary_with_assignment(self, async_client: AsyncClient) -> None:
        """Accrual policy + assignment + triggered accrual shows balance in summary."""
        pid = await _setup_accrual_with_balance(async_client)

        resp = await async_client.get(BALANCES_URL, headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

        # Find the balance for our employee and policy
        balance = next(
            (b for b in data["items"] if b["employee_id"] == str(EMPLOYEE_ID) and b["policy_id"] == pid),
            None,
        )
        assert balance is not None
        assert balance["accrued_minutes"] == 40
        assert balance["used_minutes"] == 0
        assert balance["held_minutes"] == 0
        assert balance["available_minutes"] == 40
        assert balance["is_unlimited"] is False
        assert balance["policy_key"] == "vacation-accrual"
        assert balance["policy_category"] == "VACATION"

    async def test_balance_summary_employee_can_access(self, async_client: AsyncClient) -> None:
        """Employee role can access the balance summary (AuthDep, not AdminDep)."""
        resp = await async_client.get(BALANCES_URL, headers=EMPLOYEE_HEADERS)
        assert resp.status_code == 200


# ===========================================================================
# Ledger export tests
# ===========================================================================


class TestLedgerExport:
    """Tests for the ledger export endpoint."""

    async def test_ledger_export_empty(self, async_client: AsyncClient) -> None:
        """No ledger entries returns empty list."""
        resp = await async_client.get(LEDGER_URL, headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_ledger_export_after_adjustment(self, async_client: AsyncClient) -> None:
        """Create policy + assignment + adjustment, then ledger export returns entries."""
        # Create accrual policy
        resp = await async_client.post(
            POLICIES_URL,
            json={
                "key": "ledger-adj-policy",
                "category": "VACATION",
                "version": {
                    "effective_from": "2025-01-01",
                    "settings": {
                        "type": "ACCRUAL",
                        "accrual_method": "TIME",
                        "accrual_frequency": "DAILY",
                        "accrual_timing": "START_OF_PERIOD",
                        "rate_minutes_per_day": 40,
                    },
                },
            },
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201
        pid = resp.json()["id"]

        # Assign employee
        await async_client.post(
            f"{POLICIES_URL}/{pid}/assignments",
            json={"employee_id": str(EMPLOYEE_ID), "effective_from": "2025-01-01"},
            headers=AUTH_HEADERS,
        )

        # Create adjustment
        adj_url = f"/companies/{COMPANY_ID}/adjustments"
        adj_resp = await async_client.post(
            adj_url,
            json={
                "employee_id": str(EMPLOYEE_ID),
                "policy_id": pid,
                "amount_minutes": 480,
                "reason": "Manual grant",
            },
            headers=AUTH_HEADERS,
        )
        assert adj_resp.status_code == 201

        # Query ledger export
        resp = await async_client.get(LEDGER_URL, headers=AUTH_HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

        # Find the adjustment entry
        adjustment_entries = [e for e in data["items"] if e["entry_type"] == "ADJUSTMENT"]
        assert len(adjustment_entries) >= 1
        entry = adjustment_entries[0]
        assert entry["employee_id"] == str(EMPLOYEE_ID)
        assert entry["policy_id"] == pid
        assert entry["amount_minutes"] == 480
        assert entry["source_type"] == "ADMIN"

    async def test_ledger_export_filter_by_employee(self, async_client: AsyncClient) -> None:
        """Filter ledger export by employee_id returns only that employee's entries."""
        await _setup_accrual_with_balance(async_client)

        # Query with employee filter
        resp = await async_client.get(
            LEDGER_URL,
            params={"employee_id": str(EMPLOYEE_ID)},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        for entry in data["items"]:
            assert entry["employee_id"] == str(EMPLOYEE_ID)

        # Query with a random employee_id should return nothing
        other_emp = uuid.uuid4()
        resp2 = await async_client.get(
            LEDGER_URL,
            params={"employee_id": str(other_emp)},
            headers=AUTH_HEADERS,
        )
        assert resp2.status_code == 200
        assert resp2.json()["total"] == 0

    async def test_ledger_export_filter_by_policy(self, async_client: AsyncClient) -> None:
        """Filter ledger export by policy_id returns only that policy's entries."""
        pid = await _setup_accrual_with_balance(async_client)

        resp = await async_client.get(
            LEDGER_URL,
            params={"policy_id": pid},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        for entry in data["items"]:
            assert entry["policy_id"] == pid

    async def test_ledger_export_pagination(self, async_client: AsyncClient) -> None:
        """Test offset/limit pagination on ledger export."""
        # Create policy + assignment
        resp = await async_client.post(
            POLICIES_URL,
            json={
                "key": "ledger-page-policy",
                "category": "VACATION",
                "version": {
                    "effective_from": "2025-01-01",
                    "settings": {
                        "type": "ACCRUAL",
                        "accrual_method": "TIME",
                        "accrual_frequency": "DAILY",
                        "accrual_timing": "START_OF_PERIOD",
                        "rate_minutes_per_day": 40,
                    },
                },
            },
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 201
        pid = resp.json()["id"]

        await async_client.post(
            f"{POLICIES_URL}/{pid}/assignments",
            json={"employee_id": str(EMPLOYEE_ID), "effective_from": "2025-01-01"},
            headers=AUTH_HEADERS,
        )

        # Create multiple adjustments to generate ledger entries
        adj_url = f"/companies/{COMPANY_ID}/adjustments"
        for i in range(4):
            await async_client.post(
                adj_url,
                json={
                    "employee_id": str(EMPLOYEE_ID),
                    "policy_id": pid,
                    "amount_minutes": 100 * (i + 1),
                    "reason": f"Grant {i}",
                },
                headers=AUTH_HEADERS,
            )

        # Get first page
        resp1 = await async_client.get(
            LEDGER_URL,
            params={"offset": 0, "limit": 2},
            headers=AUTH_HEADERS,
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["total"] >= 4
        assert len(data1["items"]) == 2

        # Get second page
        resp2 = await async_client.get(
            LEDGER_URL,
            params={"offset": 2, "limit": 2},
            headers=AUTH_HEADERS,
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert len(data2["items"]) >= 1

        # Ensure pages return different entries
        page1_ids = {e["id"] for e in data1["items"]}
        page2_ids = {e["id"] for e in data2["items"]}
        assert page1_ids.isdisjoint(page2_ids)

    async def test_ledger_export_admin_only(self, async_client: AsyncClient) -> None:
        """Employee role gets 403 when querying ledger export."""
        resp = await async_client.get(LEDGER_URL, headers=EMPLOYEE_HEADERS)
        assert resp.status_code == 403
