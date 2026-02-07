# ruff: noqa: TC003
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


def _now_utc() -> datetime:
    return datetime.now(UTC)


class TimeOffBalanceSnapshot(SQLModel, table=True):
    """Derived balance cache updated transactionally with ledger writes."""

    __tablename__ = "time_off_balance_snapshot"
    __table_args__ = (sa.PrimaryKeyConstraint("company_id", "employee_id", "policy_id"),)

    company_id: uuid.UUID
    employee_id: uuid.UUID = Field(index=True)
    policy_id: uuid.UUID = Field(
        sa_column=sa.Column(sa.Uuid, sa.ForeignKey("time_off_policy.id", ondelete="CASCADE")),
    )
    accrued_minutes: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    used_minutes: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    held_minutes: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    available_minutes: int = Field(default=0, sa_column_kwargs={"server_default": "0"})
    updated_at: datetime = Field(  # type: ignore[call-overload]
        default_factory=_now_utc,
        sa_type=sa.DateTime(timezone=True),
        sa_column_kwargs={"server_default": sa.func.now(), "onupdate": sa.func.now()},
    )
    version: int = Field(default=1, sa_column_kwargs={"server_default": "1"})
