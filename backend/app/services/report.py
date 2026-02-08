"""Reporting service: audit log queries, balance summaries, and ledger exports."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import func, or_, select
from sqlmodel import col

from app.models.assignment import TimeOffPolicyAssignment
from app.models.audit import AuditLog
from app.models.balance import TimeOffBalanceSnapshot
from app.models.enums import PolicyType
from app.models.ledger import TimeOffLedgerEntry
from app.models.policy import TimeOffPolicy, TimeOffPolicyVersion
from app.schemas.report import (
    AuditLogEntryResponse,
    AuditLogListResponse,
    BalanceSummaryResponse,
    EmployeeBalanceSummary,
    LedgerExportEntry,
    LedgerExportResponse,
)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


async def query_audit_log(
    session: AsyncSession,
    company_id: uuid.UUID,
    *,
    entity_type: str | None = None,
    action: str | None = None,
    actor_id: uuid.UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    offset: int = 0,
    limit: int = 50,
) -> AuditLogListResponse:
    """Query audit log entries with optional filters."""
    filters = [col(AuditLog.company_id) == company_id]

    if entity_type is not None:
        filters.append(col(AuditLog.entity_type) == entity_type)
    if action is not None:
        filters.append(col(AuditLog.action) == action)
    if actor_id is not None:
        filters.append(col(AuditLog.actor_id) == actor_id)
    if start_date is not None:
        filters.append(col(AuditLog.created_at) >= start_date)
    if end_date is not None:
        filters.append(col(AuditLog.created_at) <= end_date)

    count_result = await session.execute(select(func.count()).select_from(AuditLog).where(*filters))
    total = count_result.scalar_one()

    result = await session.execute(
        select(AuditLog).where(*filters).order_by(col(AuditLog.created_at).desc()).offset(offset).limit(limit)
    )
    entries = list(result.scalars().all())

    return AuditLogListResponse(
        items=[
            AuditLogEntryResponse(
                id=e.id,
                company_id=e.company_id,
                actor_id=e.actor_id,
                entity_type=e.entity_type,
                entity_id=e.entity_id,
                action=e.action,
                before_json=e.before_json,
                after_json=e.after_json,
                created_at=e.created_at,
            )
            for e in entries
        ],
        total=total,
    )


async def get_company_balance_summary(
    session: AsyncSession,
    company_id: uuid.UUID,
) -> BalanceSummaryResponse:
    """Get balance summary across all employees for a company."""
    today = date.today()

    # Find all active assignments
    assignments_result = await session.execute(
        select(TimeOffPolicyAssignment)
        .where(
            col(TimeOffPolicyAssignment.company_id) == company_id,
            col(TimeOffPolicyAssignment.effective_from) <= today,
            or_(
                col(TimeOffPolicyAssignment.effective_to).is_(None),
                col(TimeOffPolicyAssignment.effective_to) > today,
            ),
        )
        .order_by(
            col(TimeOffPolicyAssignment.employee_id),
            col(TimeOffPolicyAssignment.policy_id),
        )
    )
    assignments = list(assignments_result.scalars().all())

    items: list[EmployeeBalanceSummary] = []
    for assignment in assignments:
        # Get policy metadata
        policy_result = await session.execute(
            select(TimeOffPolicy).where(col(TimeOffPolicy.id) == assignment.policy_id)
        )
        policy = policy_result.scalar_one_or_none()
        if policy is None:
            continue

        # Check if unlimited
        version_result = await session.execute(
            select(TimeOffPolicyVersion)
            .where(
                col(TimeOffPolicyVersion.policy_id) == assignment.policy_id,
                col(TimeOffPolicyVersion.effective_from) <= today,
                or_(
                    col(TimeOffPolicyVersion.effective_to).is_(None),
                    col(TimeOffPolicyVersion.effective_to) > today,
                ),
            )
            .order_by(col(TimeOffPolicyVersion.version).desc())
            .limit(1)
        )
        version = version_result.scalar_one_or_none()
        is_unlimited = version is not None and version.type == PolicyType.UNLIMITED.value

        # Get snapshot or default zeros
        snapshot_result = await session.execute(
            select(TimeOffBalanceSnapshot).where(
                col(TimeOffBalanceSnapshot.company_id) == company_id,
                col(TimeOffBalanceSnapshot.employee_id) == assignment.employee_id,
                col(TimeOffBalanceSnapshot.policy_id) == assignment.policy_id,
            )
        )
        snapshot = snapshot_result.scalar_one_or_none()

        accrued = snapshot.accrued_minutes if snapshot else 0
        used = snapshot.used_minutes if snapshot else 0
        held = snapshot.held_minutes if snapshot else 0
        available = accrued - used - held

        items.append(
            EmployeeBalanceSummary(
                employee_id=assignment.employee_id,
                policy_id=assignment.policy_id,
                policy_key=policy.key,
                policy_category=policy.category,
                accrued_minutes=accrued,
                used_minutes=used,
                held_minutes=held,
                available_minutes=None if is_unlimited else available,
                is_unlimited=is_unlimited,
            )
        )

    return BalanceSummaryResponse(items=items, total=len(items))


async def export_ledger(
    session: AsyncSession,
    company_id: uuid.UUID,
    *,
    policy_id: uuid.UUID | None = None,
    employee_id: uuid.UUID | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    offset: int = 0,
    limit: int = 50,
) -> LedgerExportResponse:
    """Export ledger entries with optional filters."""
    filters = [col(TimeOffLedgerEntry.company_id) == company_id]

    if policy_id is not None:
        filters.append(col(TimeOffLedgerEntry.policy_id) == policy_id)
    if employee_id is not None:
        filters.append(col(TimeOffLedgerEntry.employee_id) == employee_id)
    if start_date is not None:
        filters.append(col(TimeOffLedgerEntry.effective_at) >= start_date)
    if end_date is not None:
        filters.append(col(TimeOffLedgerEntry.effective_at) <= end_date)

    count_result = await session.execute(select(func.count()).select_from(TimeOffLedgerEntry).where(*filters))
    total = count_result.scalar_one()

    result = await session.execute(
        select(TimeOffLedgerEntry)
        .where(*filters)
        .order_by(col(TimeOffLedgerEntry.effective_at).desc(), col(TimeOffLedgerEntry.created_at).desc())
        .offset(offset)
        .limit(limit)
    )
    entries = list(result.scalars().all())

    return LedgerExportResponse(
        items=[
            LedgerExportEntry(
                id=e.id,
                employee_id=e.employee_id,
                policy_id=e.policy_id,
                entry_type=e.entry_type,
                amount_minutes=e.amount_minutes,
                effective_at=e.effective_at,
                source_type=e.source_type,
                source_id=e.source_id,
                metadata_json=e.metadata_json,
                created_at=e.created_at,
            )
            for e in entries
        ],
        total=total,
    )
