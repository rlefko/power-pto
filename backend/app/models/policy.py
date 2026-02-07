# ruff: noqa: TC003
from __future__ import annotations

import uuid
from datetime import date
from typing import Any

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import TimestampMixin, UUIDBase


class TimeOffPolicy(UUIDBase, TimestampMixin, table=True):
    """Logical grouping for a time-off policy (e.g. Vacation-FT)."""

    __tablename__ = "time_off_policy"
    __table_args__ = (sa.UniqueConstraint("company_id", "key", name="uq_policy_company_key"),)

    company_id: uuid.UUID = Field(index=True)
    key: str = Field(max_length=255)
    category: str = Field(max_length=50)


class TimeOffPolicyVersion(UUIDBase, TimestampMixin, table=True):
    """Immutable version of a policy's settings, created on every policy update."""

    __tablename__ = "time_off_policy_version"
    __table_args__ = (sa.UniqueConstraint("policy_id", "version", name="uq_policy_version_number"),)

    policy_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid, sa.ForeignKey("time_off_policy.id", ondelete="CASCADE"), nullable=False, index=True
        ),
    )
    version: int
    effective_from: date
    effective_to: date | None = None
    type: str = Field(max_length=50)
    accrual_method: str | None = Field(default=None, max_length=50)
    settings_json: dict[str, Any] | None = Field(default=None, sa_type=sa.JSON)
    created_by: uuid.UUID
    change_reason: str | None = None
