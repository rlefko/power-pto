from __future__ import annotations

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlmodel import Field, SQLModel


def _uuid_factory() -> uuid.UUID:
    """Generate a new UUID v4."""
    return uuid.uuid4()


def _now_utc() -> datetime:
    """Return the current UTC time."""
    return datetime.now(UTC)


class UUIDBase(SQLModel):
    """Base model with UUID primary key."""

    id: uuid.UUID = Field(
        default_factory=_uuid_factory,
        primary_key=True,
        sa_type=sa.Uuid,
    )


class TimestampMixin(SQLModel):
    """Mixin that adds a created_at timestamp."""

    created_at: datetime = Field(
        default_factory=_now_utc,
        sa_type=sa.DateTime(timezone=True),  # ty: ignore[invalid-argument-type]
        sa_column_kwargs={"server_default": sa.func.now()},
    )
