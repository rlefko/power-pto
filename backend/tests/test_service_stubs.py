"""Tests for Employee and Company service stubs."""

from __future__ import annotations

import uuid

from app.services.company import CompanyInfo, InMemoryCompanyService
from app.services.employee import EmployeeInfo, InMemoryEmployeeService

COMPANY_A = uuid.uuid4()
COMPANY_B = uuid.uuid4()


def _make_employee(company_id: uuid.UUID, name: str = "Jane") -> EmployeeInfo:
    return EmployeeInfo(
        id=uuid.uuid4(),
        company_id=company_id,
        first_name=name,
        last_name="Doe",
        email=f"{name.lower()}@example.com",
        pay_type="SALARY",
        workday_minutes=480,
        timezone="America/New_York",
    )


# ---------------------------------------------------------------------------
# InMemoryEmployeeService tests
# ---------------------------------------------------------------------------


async def test_employee_service_get_not_found() -> None:
    svc = InMemoryEmployeeService()
    result = await svc.get_employee(COMPANY_A, uuid.uuid4())
    assert result is None


async def test_employee_service_seed_and_get() -> None:
    svc = InMemoryEmployeeService()
    emp = _make_employee(COMPANY_A)
    svc.seed(emp)
    result = await svc.get_employee(COMPANY_A, emp.id)
    assert result is not None
    assert result.id == emp.id
    assert result.company_id == COMPANY_A


async def test_employee_service_list_empty() -> None:
    svc = InMemoryEmployeeService()
    result = await svc.list_employees(COMPANY_A)
    assert result == []


async def test_employee_service_list_filters_by_company() -> None:
    svc = InMemoryEmployeeService()
    emp_a = _make_employee(COMPANY_A, "Alice")
    emp_b = _make_employee(COMPANY_B, "Bob")
    svc.seed(emp_a)
    svc.seed(emp_b)

    result_a = await svc.list_employees(COMPANY_A)
    assert len(result_a) == 1
    assert result_a[0].id == emp_a.id

    result_b = await svc.list_employees(COMPANY_B)
    assert len(result_b) == 1
    assert result_b[0].id == emp_b.id


# ---------------------------------------------------------------------------
# InMemoryCompanyService tests
# ---------------------------------------------------------------------------


async def test_company_service_get_not_found() -> None:
    svc = InMemoryCompanyService()
    result = await svc.get_company(uuid.uuid4())
    assert result is None


async def test_company_service_seed_and_get() -> None:
    svc = InMemoryCompanyService()
    company = CompanyInfo(
        id=COMPANY_A,
        name="Acme Corp",
        timezone="America/New_York",
        default_workday_minutes=480,
    )
    svc.seed(company)
    result = await svc.get_company(COMPANY_A)
    assert result is not None
    assert result.id == COMPANY_A
    assert result.name == "Acme Corp"
