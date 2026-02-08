# ruff: noqa: TC003
from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, Field


class UpsertEmployeeRequest(BaseModel):
    """Request body for upserting an employee in the stub service."""

    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=1, max_length=255)
    pay_type: str = Field(default="SALARY", pattern=r"^(SALARY|HOURLY)$")
    workday_minutes: int = Field(default=480, ge=60, le=1440)
    timezone: str = Field(default="UTC", min_length=1)
    hire_date: date | None = None


class EmployeeResponse(BaseModel):
    """Response schema for an employee."""

    id: uuid.UUID
    company_id: uuid.UUID
    first_name: str
    last_name: str
    email: str
    pay_type: str
    workday_minutes: int
    timezone: str
    hire_date: date | None


class EmployeeListResponse(BaseModel):
    """List of employees."""

    items: list[EmployeeResponse]
    total: int
