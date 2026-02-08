"""Integration tests for policy CRUD, versioning, and audit."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from httpx import AsyncClient

COMPANY_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
AUTH_HEADERS = {
    "X-Company-Id": str(COMPANY_ID),
    "X-User-Id": str(USER_ID),
    "X-Role": "admin",
}
BASE_URL = f"/companies/{COMPANY_ID}/policies"


def _unlimited_payload(key: str = "unlimited-vacation") -> dict:  # type: ignore[type-arg]
    return {
        "key": key,
        "category": "VACATION",
        "version": {
            "effective_from": "2025-01-01",
            "settings": {"type": "UNLIMITED"},
        },
    }


def _time_accrual_payload(key: str = "vacation-ft") -> dict:  # type: ignore[type-arg]
    return {
        "key": key,
        "category": "VACATION",
        "version": {
            "effective_from": "2025-01-01",
            "settings": {
                "type": "ACCRUAL",
                "accrual_method": "TIME",
                "accrual_frequency": "MONTHLY",
                "rate_minutes_per_month": 800,
                "bank_cap_minutes": 14400,
            },
            "change_reason": "Initial policy creation",
        },
    }


def _hours_worked_payload(key: str = "sick-hourly") -> dict:  # type: ignore[type-arg]
    return {
        "key": key,
        "category": "SICK",
        "version": {
            "effective_from": "2025-01-01",
            "settings": {
                "type": "ACCRUAL",
                "accrual_method": "HOURS_WORKED",
                "accrual_ratio": {"accrue_minutes": 60, "per_worked_minutes": 1440},
            },
        },
    }


# ---------------------------------------------------------------------------
# Create policy tests
# ---------------------------------------------------------------------------


async def test_create_unlimited_policy(async_client: AsyncClient) -> None:
    resp = await async_client.post(BASE_URL, json=_unlimited_payload(), headers=AUTH_HEADERS)
    assert resp.status_code == 201
    data = resp.json()
    assert data["key"] == "unlimited-vacation"
    assert data["category"] == "VACATION"
    assert data["company_id"] == str(COMPANY_ID)
    cv = data["current_version"]
    assert cv is not None
    assert cv["version"] == 1
    assert cv["type"] == "UNLIMITED"
    assert cv["accrual_method"] is None
    assert cv["effective_to"] is None
    assert cv["settings"]["type"] == "UNLIMITED"


async def test_create_time_accrual_policy(async_client: AsyncClient) -> None:
    resp = await async_client.post(BASE_URL, json=_time_accrual_payload(), headers=AUTH_HEADERS)
    assert resp.status_code == 201
    data = resp.json()
    cv = data["current_version"]
    assert cv["type"] == "ACCRUAL"
    assert cv["accrual_method"] == "TIME"
    assert cv["settings"]["accrual_frequency"] == "MONTHLY"
    assert cv["settings"]["rate_minutes_per_month"] == 800
    assert cv["settings"]["bank_cap_minutes"] == 14400
    assert cv["change_reason"] == "Initial policy creation"


async def test_create_hours_worked_policy(async_client: AsyncClient) -> None:
    resp = await async_client.post(BASE_URL, json=_hours_worked_payload(), headers=AUTH_HEADERS)
    assert resp.status_code == 201
    data = resp.json()
    cv = data["current_version"]
    assert cv["type"] == "ACCRUAL"
    assert cv["accrual_method"] == "HOURS_WORKED"
    assert cv["settings"]["accrual_ratio"]["accrue_minutes"] == 60
    assert cv["settings"]["accrual_ratio"]["per_worked_minutes"] == 1440


async def test_create_policy_duplicate_key(async_client: AsyncClient) -> None:
    payload = _unlimited_payload(key="dup-key")
    resp1 = await async_client.post(BASE_URL, json=payload, headers=AUTH_HEADERS)
    assert resp1.status_code == 201
    resp2 = await async_client.post(BASE_URL, json=payload, headers=AUTH_HEADERS)
    assert resp2.status_code == 409


async def test_create_policy_missing_fields(async_client: AsyncClient) -> None:
    resp = await async_client.post(BASE_URL, json={"key": "test"}, headers=AUTH_HEADERS)
    assert resp.status_code == 422


async def test_create_policy_invalid_category(async_client: AsyncClient) -> None:
    payload = _unlimited_payload()
    payload["category"] = "INVALID"
    resp = await async_client.post(BASE_URL, json=payload, headers=AUTH_HEADERS)
    assert resp.status_code == 422


async def test_create_policy_invalid_settings(async_client: AsyncClient) -> None:
    payload = _unlimited_payload()
    payload["version"]["settings"] = {"type": "ACCRUAL", "accrual_method": "TIME"}
    resp = await async_client.post(BASE_URL, json=payload, headers=AUTH_HEADERS)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Get policy tests
# ---------------------------------------------------------------------------


async def test_get_policy(async_client: AsyncClient) -> None:
    create_resp = await async_client.post(BASE_URL, json=_unlimited_payload(), headers=AUTH_HEADERS)
    assert create_resp.status_code == 201
    policy_id = create_resp.json()["id"]

    resp = await async_client.get(f"{BASE_URL}/{policy_id}", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == policy_id
    assert data["current_version"] is not None


async def test_get_policy_not_found(async_client: AsyncClient) -> None:
    fake_id = uuid.uuid4()
    resp = await async_client.get(f"{BASE_URL}/{fake_id}", headers=AUTH_HEADERS)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# List policies tests
# ---------------------------------------------------------------------------


async def test_list_policies_empty(async_client: AsyncClient) -> None:
    resp = await async_client.get(BASE_URL, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_list_policies_returns_created(async_client: AsyncClient) -> None:
    await async_client.post(BASE_URL, json=_unlimited_payload(key="p1"), headers=AUTH_HEADERS)
    await async_client.post(BASE_URL, json=_time_accrual_payload(key="p2"), headers=AUTH_HEADERS)

    resp = await async_client.get(BASE_URL, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


async def test_list_policies_pagination(async_client: AsyncClient) -> None:
    for i in range(3):
        await async_client.post(BASE_URL, json=_unlimited_payload(key=f"page-{i}"), headers=AUTH_HEADERS)

    resp = await async_client.get(f"{BASE_URL}?offset=0&limit=2", headers=AUTH_HEADERS)
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2

    resp2 = await async_client.get(f"{BASE_URL}?offset=2&limit=2", headers=AUTH_HEADERS)
    data2 = resp2.json()
    assert len(data2["items"]) == 1


async def test_list_policies_does_not_leak_other_company(async_client: AsyncClient) -> None:
    await async_client.post(BASE_URL, json=_unlimited_payload(), headers=AUTH_HEADERS)

    other_company = uuid.uuid4()
    other_headers = {
        "X-Company-Id": str(other_company),
        "X-User-Id": str(USER_ID),
        "X-Role": "admin",
    }
    other_url = f"/companies/{other_company}/policies"
    resp = await async_client.get(other_url, headers=other_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


# ---------------------------------------------------------------------------
# Update (versioning) tests
# ---------------------------------------------------------------------------


async def test_update_policy_creates_new_version(async_client: AsyncClient) -> None:
    create_resp = await async_client.post(BASE_URL, json=_unlimited_payload(), headers=AUTH_HEADERS)
    assert create_resp.status_code == 201
    policy_id = create_resp.json()["id"]

    update_payload = {
        "version": {
            "effective_from": "2025-07-01",
            "settings": {
                "type": "ACCRUAL",
                "accrual_method": "TIME",
                "accrual_frequency": "MONTHLY",
                "rate_minutes_per_month": 800,
            },
            "change_reason": "Switched to accrual",
        },
    }
    resp = await async_client.put(f"{BASE_URL}/{policy_id}", json=update_payload, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    cv = data["current_version"]
    assert cv["version"] == 2
    assert cv["type"] == "ACCRUAL"
    assert cv["accrual_method"] == "TIME"
    assert cv["effective_to"] is None
    assert cv["change_reason"] == "Switched to accrual"


async def test_update_policy_end_dates_previous_version(async_client: AsyncClient) -> None:
    create_resp = await async_client.post(BASE_URL, json=_unlimited_payload(), headers=AUTH_HEADERS)
    policy_id = create_resp.json()["id"]

    update_payload = {
        "version": {
            "effective_from": "2025-07-01",
            "settings": {"type": "UNLIMITED"},
        },
    }
    await async_client.put(f"{BASE_URL}/{policy_id}", json=update_payload, headers=AUTH_HEADERS)

    # Check that v1 is now end-dated via the versions list
    versions_resp = await async_client.get(f"{BASE_URL}/{policy_id}/versions", headers=AUTH_HEADERS)
    versions = versions_resp.json()["items"]
    assert len(versions) == 2
    # Versions are ordered desc, so v2 first
    v2 = versions[0]
    v1 = versions[1]
    assert v2["version"] == 2
    assert v2["effective_to"] is None
    assert v1["version"] == 1
    assert v1["effective_to"] == "2025-07-01"


async def test_update_policy_increments_version_number(async_client: AsyncClient) -> None:
    create_resp = await async_client.post(BASE_URL, json=_unlimited_payload(), headers=AUTH_HEADERS)
    policy_id = create_resp.json()["id"]

    for i in range(3):
        update_payload = {
            "version": {
                "effective_from": f"2025-0{i + 2}-01",
                "settings": {"type": "UNLIMITED"},
            },
        }
        resp = await async_client.put(f"{BASE_URL}/{policy_id}", json=update_payload, headers=AUTH_HEADERS)
        assert resp.json()["current_version"]["version"] == i + 2


async def test_update_policy_not_found(async_client: AsyncClient) -> None:
    fake_id = uuid.uuid4()
    update_payload = {
        "version": {
            "effective_from": "2025-07-01",
            "settings": {"type": "UNLIMITED"},
        },
    }
    resp = await async_client.put(f"{BASE_URL}/{fake_id}", json=update_payload, headers=AUTH_HEADERS)
    assert resp.status_code == 404


async def test_update_policy_effective_from_before_current(async_client: AsyncClient) -> None:
    create_resp = await async_client.post(BASE_URL, json=_time_accrual_payload(), headers=AUTH_HEADERS)
    policy_id = create_resp.json()["id"]

    update_payload = {
        "version": {
            "effective_from": "2024-06-01",
            "settings": {"type": "UNLIMITED"},
        },
    }
    resp = await async_client.put(f"{BASE_URL}/{policy_id}", json=update_payload, headers=AUTH_HEADERS)
    assert resp.status_code == 400


async def test_update_policy_type_change(async_client: AsyncClient) -> None:
    """Allow changing policy type (e.g., unlimited -> accrual)."""
    create_resp = await async_client.post(BASE_URL, json=_unlimited_payload(), headers=AUTH_HEADERS)
    policy_id = create_resp.json()["id"]
    assert create_resp.json()["current_version"]["type"] == "UNLIMITED"

    update_payload = {
        "version": {
            "effective_from": "2025-07-01",
            "settings": {
                "type": "ACCRUAL",
                "accrual_method": "HOURS_WORKED",
                "accrual_ratio": {"accrue_minutes": 60, "per_worked_minutes": 1440},
            },
        },
    }
    resp = await async_client.put(f"{BASE_URL}/{policy_id}", json=update_payload, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["current_version"]["type"] == "ACCRUAL"
    assert resp.json()["current_version"]["accrual_method"] == "HOURS_WORKED"


async def test_non_admin_cannot_update(async_client: AsyncClient) -> None:
    create_resp = await async_client.post(BASE_URL, json=_unlimited_payload(), headers=AUTH_HEADERS)
    policy_id = create_resp.json()["id"]

    employee_headers = {
        "X-Company-Id": str(COMPANY_ID),
        "X-User-Id": str(USER_ID),
        "X-Role": "employee",
    }
    update_payload = {
        "version": {
            "effective_from": "2025-07-01",
            "settings": {"type": "UNLIMITED"},
        },
    }
    resp = await async_client.put(f"{BASE_URL}/{policy_id}", json=update_payload, headers=employee_headers)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# List versions tests
# ---------------------------------------------------------------------------


async def test_list_versions_returns_all(async_client: AsyncClient) -> None:
    create_resp = await async_client.post(BASE_URL, json=_unlimited_payload(), headers=AUTH_HEADERS)
    policy_id = create_resp.json()["id"]

    for i in range(2):
        update_payload = {
            "version": {
                "effective_from": f"2025-0{i + 2}-01",
                "settings": {"type": "UNLIMITED"},
            },
        }
        await async_client.put(f"{BASE_URL}/{policy_id}", json=update_payload, headers=AUTH_HEADERS)

    resp = await async_client.get(f"{BASE_URL}/{policy_id}/versions", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3
    # Ordered desc
    assert data["items"][0]["version"] == 3
    assert data["items"][1]["version"] == 2
    assert data["items"][2]["version"] == 1


async def test_list_versions_pagination(async_client: AsyncClient) -> None:
    create_resp = await async_client.post(BASE_URL, json=_unlimited_payload(), headers=AUTH_HEADERS)
    policy_id = create_resp.json()["id"]

    for i in range(3):
        update_payload = {
            "version": {
                "effective_from": f"2025-0{i + 2}-01",
                "settings": {"type": "UNLIMITED"},
            },
        }
        await async_client.put(f"{BASE_URL}/{policy_id}", json=update_payload, headers=AUTH_HEADERS)

    resp = await async_client.get(f"{BASE_URL}/{policy_id}/versions?offset=0&limit=2", headers=AUTH_HEADERS)
    data = resp.json()
    assert data["total"] == 4
    assert len(data["items"]) == 2

    resp2 = await async_client.get(f"{BASE_URL}/{policy_id}/versions?offset=2&limit=2", headers=AUTH_HEADERS)
    data2 = resp2.json()
    assert len(data2["items"]) == 2


async def test_list_versions_policy_not_found(async_client: AsyncClient) -> None:
    fake_id = uuid.uuid4()
    resp = await async_client.get(f"{BASE_URL}/{fake_id}/versions", headers=AUTH_HEADERS)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------


async def test_missing_auth_headers(async_client: AsyncClient) -> None:
    resp = await async_client.post(BASE_URL, json=_unlimited_payload())
    assert resp.status_code == 422


async def test_company_id_mismatch(async_client: AsyncClient) -> None:
    wrong_headers = {
        "X-Company-Id": str(uuid.uuid4()),
        "X-User-Id": str(USER_ID),
        "X-Role": "admin",
    }
    resp = await async_client.post(BASE_URL, json=_unlimited_payload(), headers=wrong_headers)
    assert resp.status_code == 403


async def test_non_admin_cannot_create(async_client: AsyncClient) -> None:
    employee_headers = {
        "X-Company-Id": str(COMPANY_ID),
        "X-User-Id": str(USER_ID),
        "X-Role": "employee",
    }
    resp = await async_client.post(BASE_URL, json=_unlimited_payload(), headers=employee_headers)
    assert resp.status_code == 403


async def test_employee_can_list(async_client: AsyncClient) -> None:
    employee_headers = {
        "X-Company-Id": str(COMPANY_ID),
        "X-User-Id": str(USER_ID),
        "X-Role": "employee",
    }
    resp = await async_client.get(BASE_URL, headers=employee_headers)
    assert resp.status_code == 200


async def test_employee_can_get(async_client: AsyncClient) -> None:
    create_resp = await async_client.post(BASE_URL, json=_unlimited_payload(), headers=AUTH_HEADERS)
    policy_id = create_resp.json()["id"]

    employee_headers = {
        "X-Company-Id": str(COMPANY_ID),
        "X-User-Id": str(USER_ID),
        "X-Role": "employee",
    }
    resp = await async_client.get(f"{BASE_URL}/{policy_id}", headers=employee_headers)
    assert resp.status_code == 200
