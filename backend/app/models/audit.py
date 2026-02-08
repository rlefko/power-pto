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


class AuditLog(UUIDBase, table=True):
    """Immutable record of every mutation in the system."""

    __tablename__ = "audit_log"
    __table_args__ = (sa.Index("ix_audit_entity", "entity_type", "entity_id"),)

    company_id: uuid.UUID = Field(index=True)
    actor_id: uuid.UUID
    entity_type: str = Field(max_length=50)
    entity_id: uuid.UUID
    action: str = Field(max_length=50)
    before_json: dict[str, Any] | None = Field(default=None, sa_type=sa.JSON)
    after_json: dict[str, Any] | None = Field(default=None, sa_type=sa.JSON)
    created_at: datetime = Field(
        default_factory=_now_utc,
        index=True,
        sa_type=sa.DateTime(timezone=True),  # ty: ignore[invalid-argument-type]
        sa_column_kwargs={"server_default": sa.func.now()},
    )
