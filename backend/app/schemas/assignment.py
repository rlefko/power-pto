# ruff: noqa: TC003
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, model_validator


class CreateAssignmentRequest(BaseModel):
    """Request body for assigning an employee to a policy."""

    employee_id: uuid.UUID
    effective_from: date
    effective_to: date | None = None

    @model_validator(mode="after")
    def _validate_dates(self) -> Self:
        if self.effective_to is not None and self.effective_to < self.effective_from:
            msg = "effective_to must be >= effective_from"
            raise ValueError(msg)
        return self


class AssignmentResponse(BaseModel):
    """Response schema for a single assignment."""

    id: uuid.UUID
    company_id: uuid.UUID
    employee_id: uuid.UUID
    policy_id: uuid.UUID
    effective_from: date
    effective_to: date | None
    created_by: uuid.UUID
    created_at: datetime


class AssignmentListResponse(BaseModel):
    """Paginated list of assignments."""

    items: list[AssignmentResponse]
    total: int
