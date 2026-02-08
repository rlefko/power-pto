# ruff: noqa: TC003
from __future__ import annotations

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import TimestampMixin, UUIDBase
from app.models.enums import RequestStatus


class TimeOffRequest(UUIDBase, TimestampMixin, table=True):
    """An employee's time-off request with approval workflow state."""

    __tablename__ = "time_off_request"
    __table_args__ = (
        sa.Index("ix_request_company_status", "company_id", "status"),
        sa.UniqueConstraint("company_id", "employee_id", "idempotency_key", name="uq_request_idempotency"),
    )

    company_id: uuid.UUID = Field(index=True)
    employee_id: uuid.UUID = Field(index=True)
    policy_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid, sa.ForeignKey("time_off_policy.id", ondelete="CASCADE"), nullable=False, index=True
        ),
    )
    start_at: datetime = Field(sa_type=sa.DateTime(timezone=True))  # ty: ignore[invalid-argument-type]
    end_at: datetime = Field(sa_type=sa.DateTime(timezone=True))  # ty: ignore[invalid-argument-type]
    requested_minutes: int
    reason: str | None = None
    status: str = Field(
        default=RequestStatus.DRAFT, max_length=50, index=True, sa_column_kwargs={"server_default": "DRAFT"}
    )
    submitted_at: datetime | None = Field(default=None, sa_type=sa.DateTime(timezone=True))  # ty: ignore[invalid-argument-type]
    decided_at: datetime | None = Field(default=None, sa_type=sa.DateTime(timezone=True))  # ty: ignore[invalid-argument-type]
    decided_by: uuid.UUID | None = None
    decision_note: str | None = None
    idempotency_key: str | None = Field(default=None, max_length=255)
