# ruff: noqa: TC003
from __future__ import annotations

import uuid
from datetime import date

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import TimestampMixin, UUIDBase


class TimeOffPolicyAssignment(UUIDBase, TimestampMixin, table=True):
    """Links an employee to a policy with effective dating."""

    __tablename__ = "time_off_policy_assignment"
    __table_args__ = (
        sa.UniqueConstraint(
            "company_id",
            "employee_id",
            "policy_id",
            "effective_from",
            name="uq_assignment_employee_policy_from",
        ),
    )

    company_id: uuid.UUID = Field(index=True)
    employee_id: uuid.UUID = Field(index=True)
    policy_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid, sa.ForeignKey("time_off_policy.id", ondelete="CASCADE"), nullable=False, index=True
        ),
    )
    effective_from: date
    effective_to: date | None = None
    created_by: uuid.UUID
