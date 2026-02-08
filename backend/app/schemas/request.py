# ruff: noqa: TC001, TC003
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, Field, model_validator

from app.models.enums import RequestStatus

# ---------------------------------------------------------------------------
# Request payloads
# ---------------------------------------------------------------------------


class SubmitRequestPayload(BaseModel):
    """Request body for submitting a new time-off request."""

    employee_id: uuid.UUID
    policy_id: uuid.UUID
    start_at: datetime
    end_at: datetime
    reason: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def _validate_dates(self) -> Self:
        if self.end_at <= self.start_at:
            msg = "end_at must be after start_at"
            raise ValueError(msg)
        return self


class DecisionPayload(BaseModel):
    """Request body for approve/deny actions."""

    note: str | None = Field(default=None, max_length=1000)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class RequestResponse(BaseModel):
    """Response schema for a single time-off request."""

    id: uuid.UUID
    company_id: uuid.UUID
    employee_id: uuid.UUID
    policy_id: uuid.UUID
    start_at: datetime
    end_at: datetime
    requested_minutes: int
    reason: str | None
    status: RequestStatus
    submitted_at: datetime | None
    decided_at: datetime | None
    decided_by: uuid.UUID | None
    decision_note: str | None
    idempotency_key: str | None
    created_at: datetime


class RequestListResponse(BaseModel):
    """Paginated list of time-off requests."""

    items: list[RequestResponse]
    total: int
