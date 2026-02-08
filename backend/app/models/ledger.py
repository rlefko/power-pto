# ruff: noqa: TC003
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import UUIDBase


def _now_utc() -> datetime:
    return datetime.now(UTC)


class TimeOffLedgerEntry(UUIDBase, table=True):
    """Append-only ledger entry that records every balance-affecting event."""

    __tablename__ = "time_off_ledger_entry"
    __table_args__ = (
        sa.Index("ix_ledger_employee_policy", "employee_id", "policy_id"),
        sa.UniqueConstraint("source_type", "source_id", "entry_type", name="uq_ledger_idempotency"),
    )

    company_id: uuid.UUID = Field(index=True)
    employee_id: uuid.UUID = Field(index=True)
    policy_id: uuid.UUID = Field(
        sa_column=sa.Column(
            sa.Uuid, sa.ForeignKey("time_off_policy.id", ondelete="CASCADE"), nullable=False, index=True
        ),
    )
    policy_version_id: uuid.UUID = Field(
        sa_column=sa.Column(sa.Uuid, sa.ForeignKey("time_off_policy_version.id", ondelete="CASCADE"), nullable=False),
    )
    entry_type: str = Field(max_length=50)
    amount_minutes: int
    effective_at: datetime = Field(sa_type=sa.DateTime(timezone=True))  # ty: ignore[invalid-argument-type]
    source_type: str = Field(max_length=50)
    source_id: str = Field(max_length=255)
    metadata_json: dict[str, Any] | None = Field(default=None, sa_type=sa.JSON)
    created_at: datetime = Field(
        default_factory=_now_utc,
        sa_type=sa.DateTime(timezone=True),  # ty: ignore[invalid-argument-type]
        sa_column_kwargs={"server_default": sa.func.now()},
    )
