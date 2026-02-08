"""Integration tests for holiday CRUD API, authorization, and audit."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlmodel import col

from app.models.audit import AuditLog

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

COMPANY_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
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
BASE_URL = f"/companies/{COMPANY_ID}/holidays"


def _holiday_payload(date: str = "2025-07-04", name: str = "Independence Day") -> dict:
    return {"date": date, "name": name}


# ---------------------------------------------------------------------------
# Create holiday tests
# ---------------------------------------------------------------------------


async def test_create_holiday(async_client: AsyncClient) -> None:
    resp = await async_client.post(BASE_URL, json=_holiday_payload(), headers=AUTH_HEADERS)
    assert resp.status_code == 201
    data = resp.json()
    assert data["date"] == "2025-07-04"
    assert data["name"] == "Independence Day"
    assert data["company_id"] == str(COMPANY_ID)
    assert "id" in data


# ---------------------------------------------------------------------------
# List holiday tests
# ---------------------------------------------------------------------------


async def test_list_holidays_empty(async_client: AsyncClient) -> None:
    resp = await async_client.get(BASE_URL, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_list_holidays_returns_created(async_client: AsyncClient) -> None:
    await async_client.post(
        BASE_URL,
        json=_holiday_payload("2025-07-04", "Independence Day"),
        headers=AUTH_HEADERS,
    )
    await async_client.post(
        BASE_URL,
        json=_holiday_payload("2025-12-25", "Christmas Day"),
        headers=AUTH_HEADERS,
    )

    resp = await async_client.get(BASE_URL, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


async def test_list_holidays_year_filter(async_client: AsyncClient) -> None:
    await async_client.post(
        BASE_URL,
        json=_holiday_payload("2025-12-25", "Christmas 2025"),
        headers=AUTH_HEADERS,
    )
    await async_client.post(
        BASE_URL,
        json=_holiday_payload("2026-01-01", "New Year 2026"),
        headers=AUTH_HEADERS,
    )

    resp_2025 = await async_client.get(f"{BASE_URL}?year=2025", headers=AUTH_HEADERS)
    data_2025 = resp_2025.json()
    assert data_2025["total"] == 1
    assert data_2025["items"][0]["date"] == "2025-12-25"

    resp_2026 = await async_client.get(f"{BASE_URL}?year=2026", headers=AUTH_HEADERS)
    data_2026 = resp_2026.json()
    assert data_2026["total"] == 1
    assert data_2026["items"][0]["date"] == "2026-01-01"


async def test_list_holidays_pagination(async_client: AsyncClient) -> None:
    for i in range(3):
        await async_client.post(
            BASE_URL,
            json=_holiday_payload(f"2025-0{i + 1}-01", f"Holiday {i}"),
            headers=AUTH_HEADERS,
        )

    resp = await async_client.get(f"{BASE_URL}?offset=0&limit=2", headers=AUTH_HEADERS)
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2

    resp2 = await async_client.get(f"{BASE_URL}?offset=2&limit=2", headers=AUTH_HEADERS)
    data2 = resp2.json()
    assert len(data2["items"]) == 1


# ---------------------------------------------------------------------------
# Delete holiday tests
# ---------------------------------------------------------------------------


async def test_delete_holiday(async_client: AsyncClient) -> None:
    create_resp = await async_client.post(BASE_URL, json=_holiday_payload(), headers=AUTH_HEADERS)
    assert create_resp.status_code == 201
    holiday_id = create_resp.json()["id"]

    del_resp = await async_client.delete(f"{BASE_URL}/{holiday_id}", headers=AUTH_HEADERS)
    assert del_resp.status_code == 204

    list_resp = await async_client.get(BASE_URL, headers=AUTH_HEADERS)
    assert list_resp.json()["total"] == 0
    assert list_resp.json()["items"] == []


# ---------------------------------------------------------------------------
# Duplicate / conflict tests
# ---------------------------------------------------------------------------


async def test_duplicate_date_returns_409(async_client: AsyncClient) -> None:
    payload = _holiday_payload("2025-09-01", "Labor Day")
    resp1 = await async_client.post(BASE_URL, json=payload, headers=AUTH_HEADERS)
    assert resp1.status_code == 201

    resp2 = await async_client.post(BASE_URL, json=payload, headers=AUTH_HEADERS)
    assert resp2.status_code == 409


# ---------------------------------------------------------------------------
# Authorization tests
# ---------------------------------------------------------------------------


async def test_non_admin_cannot_create(async_client: AsyncClient) -> None:
    resp = await async_client.post(BASE_URL, json=_holiday_payload(), headers=EMPLOYEE_HEADERS)
    assert resp.status_code == 403


async def test_non_admin_cannot_delete(async_client: AsyncClient) -> None:
    create_resp = await async_client.post(BASE_URL, json=_holiday_payload(), headers=AUTH_HEADERS)
    assert create_resp.status_code == 201
    holiday_id = create_resp.json()["id"]

    del_resp = await async_client.delete(f"{BASE_URL}/{holiday_id}", headers=EMPLOYEE_HEADERS)
    assert del_resp.status_code == 403


async def test_employee_can_list(async_client: AsyncClient) -> None:
    resp = await async_client.get(BASE_URL, headers=EMPLOYEE_HEADERS)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Company isolation tests
# ---------------------------------------------------------------------------


async def test_company_isolation(async_client: AsyncClient) -> None:
    await async_client.post(BASE_URL, json=_holiday_payload(), headers=AUTH_HEADERS)

    other_company = uuid.uuid4()
    other_headers = {
        "X-Company-Id": str(other_company),
        "X-User-Id": str(USER_ID),
        "X-Role": "admin",
    }
    other_url = f"/companies/{other_company}/holidays"
    resp = await async_client.get(other_url, headers=other_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 0
    assert resp.json()["items"] == []


# ---------------------------------------------------------------------------
# Audit tests
# ---------------------------------------------------------------------------


async def test_create_holiday_writes_audit(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    resp = await async_client.post(BASE_URL, json=_holiday_payload(), headers=AUTH_HEADERS)
    assert resp.status_code == 201
    holiday_id = resp.json()["id"]

    result = await db_session.execute(
        select(AuditLog).where(
            col(AuditLog.entity_type) == "HOLIDAY",
            col(AuditLog.action) == "CREATE",
            col(AuditLog.company_id) == COMPANY_ID,
        )
    )
    audit = result.scalar_one()
    assert audit.company_id == COMPANY_ID
    assert str(audit.actor_id) == str(USER_ID)
    assert str(audit.entity_id) == holiday_id
    assert audit.before_json is None
    assert audit.after_json is not None
    assert audit.after_json["name"] == "Independence Day"


async def test_delete_holiday_writes_audit(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    create_resp = await async_client.post(BASE_URL, json=_holiday_payload(), headers=AUTH_HEADERS)
    assert create_resp.status_code == 201
    holiday_id = create_resp.json()["id"]

    del_resp = await async_client.delete(f"{BASE_URL}/{holiday_id}", headers=AUTH_HEADERS)
    assert del_resp.status_code == 204

    result = await db_session.execute(
        select(AuditLog).where(
            col(AuditLog.entity_type) == "HOLIDAY",
            col(AuditLog.action) == "DELETE",
            col(AuditLog.company_id) == COMPANY_ID,
        )
    )
    audit = result.scalar_one()
    assert audit.company_id == COMPANY_ID
    assert str(audit.actor_id) == str(USER_ID)
    assert str(audit.entity_id) == holiday_id
    assert audit.before_json is not None
    assert audit.before_json["name"] == "Independence Day"
    assert audit.after_json is None
