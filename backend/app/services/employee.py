# ruff: noqa: TC003
from __future__ import annotations

import uuid
from datetime import date
from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class EmployeeInfo(BaseModel):
    """Employee metadata from the Employee Service."""

    id: uuid.UUID
    company_id: uuid.UUID
    first_name: str
    last_name: str
    email: str
    pay_type: str  # "SALARY" or "HOURLY"
    workday_minutes: int  # e.g. 480 for 8-hour day
    timezone: str  # e.g. "America/New_York"
    hire_date: date | None = None  # for tenure tier lookups


@runtime_checkable
class EmployeeService(Protocol):
    """Interface for the Employee Service."""

    async def get_employee(self, company_id: uuid.UUID, employee_id: uuid.UUID) -> EmployeeInfo | None:
        """Fetch employee metadata. Returns None if not found."""
        ...

    async def list_employees(self, company_id: uuid.UUID) -> list[EmployeeInfo]:
        """List all employees for a company."""
        ...


class InMemoryEmployeeService:
    """In-memory stub implementation for development."""

    def __init__(self) -> None:
        self._employees: dict[tuple[uuid.UUID, uuid.UUID], EmployeeInfo] = {}

    def seed(self, employee: EmployeeInfo) -> None:
        """Seed an employee for testing."""
        self._employees[(employee.company_id, employee.id)] = employee

    async def get_employee(self, company_id: uuid.UUID, employee_id: uuid.UUID) -> EmployeeInfo | None:
        """Fetch employee metadata. Returns None if not found."""
        return self._employees.get((company_id, employee_id))

    async def list_employees(self, company_id: uuid.UUID) -> list[EmployeeInfo]:
        """List all employees for a company."""
        return [e for e in self._employees.values() if e.company_id == company_id]


_employee_service: EmployeeService = InMemoryEmployeeService()


def get_employee_service() -> EmployeeService:
    """FastAPI dependency for the Employee Service."""
    return _employee_service


def set_employee_service(service: EmployeeService) -> None:
    """Override the service (for testing or production wiring)."""
    global _employee_service
    _employee_service = service
