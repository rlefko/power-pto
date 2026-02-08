# ruff: noqa: TC003
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditLogEntryResponse(BaseModel):
    """Response schema for a single audit log entry."""

    id: uuid.UUID
    company_id: uuid.UUID
    actor_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    action: str
    before_json: dict[str, Any] | None
    after_json: dict[str, Any] | None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    """Paginated list of audit log entries."""

    items: list[AuditLogEntryResponse]
    total: int


class EmployeeBalanceSummary(BaseModel):
    """Balance summary for a single employee + policy."""

    employee_id: uuid.UUID
    policy_id: uuid.UUID
    policy_key: str
    policy_category: str
    accrued_minutes: int
    used_minutes: int
    held_minutes: int
    available_minutes: int | None
    is_unlimited: bool


class BalanceSummaryResponse(BaseModel):
    """Balance summary across all employees."""

    items: list[EmployeeBalanceSummary]
    total: int


class LedgerExportEntry(BaseModel):
    """Ledger entry for export."""

    id: uuid.UUID
    employee_id: uuid.UUID
    policy_id: uuid.UUID
    entry_type: str
    amount_minutes: int
    effective_at: datetime
    source_type: str
    source_id: str
    metadata_json: dict[str, Any] | None
    created_at: datetime


class LedgerExportResponse(BaseModel):
    """Paginated ledger export."""

    items: list[LedgerExportEntry]
    total: int
