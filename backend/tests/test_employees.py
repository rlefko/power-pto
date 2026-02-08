"""Integration tests for employee management API (upsert, get, list)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest

from app.services.employee import InMemoryEmployeeService, set_employee_service

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
EMPLOYEES_URL = f"/companies/{COMPANY_ID}/employees"


@pytest.fixture(autouse=True)
def _reset_employee_service() -> Iterator[None]:
    set_employee_service(InMemoryEmployeeService())
    yield
    set_employee_service(InMemoryEmployeeService())


def _employee_payload(
    first_name: str = "John",
    last_name: str = "Doe",
    email: str = "john@example.com",
    pay_type: str = "SALARY",
    workday_minutes: int = 480,
    timezone: str = "America/New_York",
    hire_date: str = "2024-01-01",
) -> dict:
    return {
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "pay_type": pay_type,
        "workday_minutes": workday_minutes,
        "timezone": timezone,
        "hire_date": hire_date,
    }


# ---------------------------------------------------------------------------
# Upsert tests
# ---------------------------------------------------------------------------


async def test_upsert_employee(async_client: AsyncClient) -> None:
    """PUT creates an employee and returns expected fields."""
    resp = await async_client.put(
        f"{EMPLOYEES_URL}/{EMPLOYEE_ID}",
        json=_employee_payload(),
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(EMPLOYEE_ID)
    assert data["company_id"] == str(COMPANY_ID)
    assert data["first_name"] == "John"
    assert data["last_name"] == "Doe"
    assert data["email"] == "john@example.com"
    assert data["pay_type"] == "SALARY"
    assert data["workday_minutes"] == 480
    assert data["timezone"] == "America/New_York"
    assert data["hire_date"] == "2024-01-01"


async def test_upsert_employee_update(async_client: AsyncClient) -> None:
    """PUT twice updates the employee fields on the second call."""
    url = f"{EMPLOYEES_URL}/{EMPLOYEE_ID}"

    resp1 = await async_client.put(
        url,
        json=_employee_payload(),
        headers=AUTH_HEADERS,
    )
    assert resp1.status_code == 200
    assert resp1.json()["first_name"] == "John"

    resp2 = await async_client.put(
        url,
        json=_employee_payload(first_name="Jane", email="jane@example.com"),
        headers=AUTH_HEADERS,
    )
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["first_name"] == "Jane"
    assert data["email"] == "jane@example.com"
    assert data["id"] == str(EMPLOYEE_ID)


# ---------------------------------------------------------------------------
# Get tests
# ---------------------------------------------------------------------------


async def test_get_employee(async_client: AsyncClient) -> None:
    """GET returns the employee created by PUT."""
    url = f"{EMPLOYEES_URL}/{EMPLOYEE_ID}"

    put_resp = await async_client.put(
        url,
        json=_employee_payload(),
        headers=AUTH_HEADERS,
    )
    assert put_resp.status_code == 200

    get_resp = await async_client.get(url, headers=AUTH_HEADERS)
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["id"] == str(EMPLOYEE_ID)
    assert data["first_name"] == "John"
    assert data["last_name"] == "Doe"
    assert data["email"] == "john@example.com"
    assert data["pay_type"] == "SALARY"
    assert data["workday_minutes"] == 480
    assert data["timezone"] == "America/New_York"
    assert data["hire_date"] == "2024-01-01"


async def test_get_employee_not_found(async_client: AsyncClient) -> None:
    """GET for a non-existent employee returns 404."""
    unknown_id = uuid.uuid4()
    resp = await async_client.get(
        f"{EMPLOYEES_URL}/{unknown_id}",
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# List tests
# ---------------------------------------------------------------------------


async def test_list_employees_empty(async_client: AsyncClient) -> None:
    """GET list with no employees returns an empty list."""
    resp = await async_client.get(EMPLOYEES_URL, headers=AUTH_HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_list_employees_returns_created(async_client: AsyncClient) -> None:
    """GET list returns all employees created via PUT."""
    emp1_id = uuid.uuid4()
    emp2_id = uuid.uuid4()

    resp1 = await async_client.put(
        f"{EMPLOYEES_URL}/{emp1_id}",
        json=_employee_payload(first_name="Alice", email="alice@example.com"),
        headers=AUTH_HEADERS,
    )
    assert resp1.status_code == 200

    resp2 = await async_client.put(
        f"{EMPLOYEES_URL}/{emp2_id}",
        json=_employee_payload(first_name="Bob", email="bob@example.com"),
        headers=AUTH_HEADERS,
    )
    assert resp2.status_code == 200

    list_resp = await async_client.get(EMPLOYEES_URL, headers=AUTH_HEADERS)
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total"] == 2
    returned_ids = {item["id"] for item in data["items"]}
    assert str(emp1_id) in returned_ids
    assert str(emp2_id) in returned_ids


# ---------------------------------------------------------------------------
# Custom workday minutes
# ---------------------------------------------------------------------------


async def test_upsert_employee_custom_workday(async_client: AsyncClient) -> None:
    """PUT with workday_minutes=360 persists the custom value."""
    url = f"{EMPLOYEES_URL}/{EMPLOYEE_ID}"

    resp = await async_client.put(
        url,
        json=_employee_payload(workday_minutes=360),
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    assert resp.json()["workday_minutes"] == 360

    get_resp = await async_client.get(url, headers=AUTH_HEADERS)
    assert get_resp.status_code == 200
    assert get_resp.json()["workday_minutes"] == 360


# ---------------------------------------------------------------------------
# Authorization tests
# ---------------------------------------------------------------------------


async def test_upsert_employee_non_admin_forbidden(async_client: AsyncClient) -> None:
    """PUT with employee role returns 403."""
    resp = await async_client.put(
        f"{EMPLOYEES_URL}/{EMPLOYEE_ID}",
        json=_employee_payload(),
        headers=EMPLOYEE_HEADERS,
    )
    assert resp.status_code == 403


async def test_employee_can_get(async_client: AsyncClient) -> None:
    """Employee role can GET a specific employee."""
    url = f"{EMPLOYEES_URL}/{EMPLOYEE_ID}"

    put_resp = await async_client.put(
        url,
        json=_employee_payload(),
        headers=AUTH_HEADERS,
    )
    assert put_resp.status_code == 200

    get_resp = await async_client.get(url, headers=EMPLOYEE_HEADERS)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == str(EMPLOYEE_ID)
    assert get_resp.json()["first_name"] == "John"


async def test_employee_can_list(async_client: AsyncClient) -> None:
    """Employee role can list employees."""
    resp = await async_client.put(
        f"{EMPLOYEES_URL}/{EMPLOYEE_ID}",
        json=_employee_payload(),
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200

    list_resp = await async_client.get(EMPLOYEES_URL, headers=EMPLOYEE_HEADERS)
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total"] == 1
    assert data["items"][0]["id"] == str(EMPLOYEE_ID)
