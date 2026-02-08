# ruff: noqa: TC003
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends

from app.api.deps import AdminDep, AuthDep, validate_company_scope
from app.schemas.employee import EmployeeListResponse, EmployeeResponse, UpsertEmployeeRequest
from app.services.employee import EmployeeInfo, get_employee_service

employees_router = APIRouter(
    prefix="/companies/{company_id}/employees",
    tags=["employees"],
    dependencies=[Depends(validate_company_scope)],
)


@employees_router.put(
    "/{employee_id}",
    response_model=EmployeeResponse,
)
async def upsert_employee(
    company_id: uuid.UUID,
    employee_id: uuid.UUID,
    payload: UpsertEmployeeRequest,
    auth: AdminDep,
) -> EmployeeResponse:
    """Create or update an employee in the stub service (admin only)."""
    svc = get_employee_service()
    employee = EmployeeInfo(
        id=employee_id,
        company_id=company_id,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        pay_type=payload.pay_type,
        workday_minutes=payload.workday_minutes,
        timezone=payload.timezone,
        hire_date=payload.hire_date,
    )
    svc.seed(employee)  # ty: ignore[unresolved-attribute]
    return EmployeeResponse(
        id=employee.id,
        company_id=employee.company_id,
        first_name=employee.first_name,
        last_name=employee.last_name,
        email=employee.email,
        pay_type=employee.pay_type,
        workday_minutes=employee.workday_minutes,
        timezone=employee.timezone,
        hire_date=employee.hire_date,
    )


@employees_router.get(
    "/{employee_id}",
    response_model=EmployeeResponse,
)
async def get_employee(
    company_id: uuid.UUID,
    employee_id: uuid.UUID,
    auth: AuthDep,
) -> EmployeeResponse:
    """Get employee info from the stub service."""
    from app.exceptions import AppError

    svc = get_employee_service()
    employee = await svc.get_employee(company_id, employee_id)
    if employee is None:
        raise AppError("Employee not found", status_code=404)
    return EmployeeResponse(
        id=employee.id,
        company_id=employee.company_id,
        first_name=employee.first_name,
        last_name=employee.last_name,
        email=employee.email,
        pay_type=employee.pay_type,
        workday_minutes=employee.workday_minutes,
        timezone=employee.timezone,
        hire_date=employee.hire_date,
    )


@employees_router.get(
    "",
    response_model=EmployeeListResponse,
)
async def list_employees(
    company_id: uuid.UUID,
    auth: AuthDep,
) -> EmployeeListResponse:
    """List all employees for a company from the stub service."""
    svc = get_employee_service()
    employees = await svc.list_employees(company_id)
    items = [
        EmployeeResponse(
            id=e.id,
            company_id=e.company_id,
            first_name=e.first_name,
            last_name=e.last_name,
            email=e.email,
            pay_type=e.pay_type,
            workday_minutes=e.workday_minutes,
            timezone=e.timezone,
            hire_date=e.hire_date,
        )
        for e in employees
    ]
    return EmployeeListResponse(items=items, total=len(items))
