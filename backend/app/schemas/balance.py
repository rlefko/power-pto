# ruff: noqa: TC001, TC003
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import LedgerEntryType, LedgerSourceType

# ---------------------------------------------------------------------------
# Balance response schemas
# ---------------------------------------------------------------------------


class BalanceResponse(BaseModel):
    """Balance for a single policy assignment."""

    policy_id: uuid.UUID
    policy_key: str
    policy_category: str
    accrued_minutes: int
    used_minutes: int
    held_minutes: int
    available_minutes: int | None  # None for unlimited policies
    is_unlimited: bool
    updated_at: datetime | None


class BalanceListResponse(BaseModel):
    """All policy balances for an employee."""

    items: list[BalanceResponse]
    total: int


# ---------------------------------------------------------------------------
# Ledger response schemas
# ---------------------------------------------------------------------------


class LedgerEntryResponse(BaseModel):
    """A single ledger entry."""

    id: uuid.UUID
    policy_id: uuid.UUID
    policy_version_id: uuid.UUID
    entry_type: LedgerEntryType
    amount_minutes: int
    effective_at: datetime
    source_type: LedgerSourceType
    source_id: str
    metadata_json: dict[str, Any] | None
    created_at: datetime


class LedgerListResponse(BaseModel):
    """Paginated ledger entries."""

    items: list[LedgerEntryResponse]
    total: int


# ---------------------------------------------------------------------------
# Adjustment request schema
# ---------------------------------------------------------------------------


class CreateAdjustmentRequest(BaseModel):
    """Request body for creating an admin balance adjustment."""

    employee_id: uuid.UUID
    policy_id: uuid.UUID
    amount_minutes: int = Field(
        description="Signed integer: positive to add, negative to deduct",
    )
    reason: str = Field(min_length=1, max_length=1000)
