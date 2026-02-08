# ruff: noqa: TC003
from __future__ import annotations

import uuid
from datetime import date
from typing import Self

from pydantic import BaseModel, Field, model_validator


class PayrollEmployeeEntry(BaseModel):
    """One employee's hours in a payroll run."""

    employee_id: uuid.UUID
    worked_minutes: int = Field(gt=0)


class PayrollProcessedPayload(BaseModel):
    """Payload for POST /webhooks/payroll_processed."""

    payroll_run_id: str = Field(min_length=1, max_length=255)
    company_id: uuid.UUID
    period_start: date
    period_end: date
    entries: list[PayrollEmployeeEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_dates(self) -> Self:
        if self.period_end < self.period_start:
            msg = "period_end must be >= period_start"
            raise ValueError(msg)
        return self


class AccrualRunResponse(BaseModel):
    """Response from the accrual trigger endpoint."""

    target_date: date
    processed: int
    accrued: int
    skipped: int
    errors: int


class PayrollProcessingResponse(BaseModel):
    """Response from the payroll webhook."""

    payroll_run_id: str
    processed: int
    accrued: int
    skipped: int
    errors: int


class CarryoverRunResponse(BaseModel):
    """Response from the carryover/expiration trigger endpoints."""

    target_date: date
    carryovers_processed: int
    expirations_processed: int
    skipped: int
    errors: int
