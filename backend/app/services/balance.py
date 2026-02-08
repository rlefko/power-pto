from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from pydantic import TypeAdapter
from sqlalchemy import case, func, or_, select
from sqlmodel import col

from app.exceptions import AppError
from app.models.assignment import TimeOffPolicyAssignment
from app.models.balance import TimeOffBalanceSnapshot
from app.models.enums import (
    AuditAction,
    AuditEntityType,
    LedgerEntryType,
    LedgerSourceType,
    PolicyType,
)
from app.models.ledger import TimeOffLedgerEntry
from app.models.policy import TimeOffPolicy
from app.schemas.balance import (
    BalanceListResponse,
    BalanceResponse,
    LedgerEntryResponse,
    LedgerListResponse,
)
from app.schemas.policy import PolicySettings
from app.services.assignment import verify_active_assignment
from app.services.audit import model_to_audit_dict, write_audit_log
from app.services.policy import _get_current_version

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas.auth import AuthContext
    from app.schemas.balance import CreateAdjustmentRequest

_settings_adapter: TypeAdapter[PolicySettings] = TypeAdapter(PolicySettings)

# Entry types that contribute to the accrued total (signed amounts).
_ACCRUAL_TYPES = [
    LedgerEntryType.ACCRUAL.value,
    LedgerEntryType.ADJUSTMENT.value,
    LedgerEntryType.CARRYOVER.value,
    LedgerEntryType.EXPIRATION.value,
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_ledger_entry_response(entry: TimeOffLedgerEntry) -> LedgerEntryResponse:
    """Map a ledger entry model to its response schema."""
    return LedgerEntryResponse(
        id=entry.id,
        policy_id=entry.policy_id,
        policy_version_id=entry.policy_version_id,
        entry_type=LedgerEntryType(entry.entry_type),
        amount_minutes=entry.amount_minutes,
        effective_at=entry.effective_at,
        source_type=LedgerSourceType(entry.source_type),
        source_id=entry.source_id,
        metadata_json=entry.metadata_json,
        created_at=entry.created_at,
    )


async def _compute_balance_from_ledger(
    session: AsyncSession,
    company_id: uuid.UUID,
    employee_id: uuid.UUID,
    policy_id: uuid.UUID,
) -> tuple[int, int, int]:
    """Recompute (accrued, used, held) from ledger entries.

    This is the fallback when no balance snapshot exists.
    """
    base_filter = [
        col(TimeOffLedgerEntry.company_id) == company_id,
        col(TimeOffLedgerEntry.employee_id) == employee_id,
        col(TimeOffLedgerEntry.policy_id) == policy_id,
    ]

    query = select(
        func.coalesce(
            func.sum(
                case(
                    (
                        col(TimeOffLedgerEntry.entry_type).in_(_ACCRUAL_TYPES),
                        col(TimeOffLedgerEntry.amount_minutes),
                    ),
                    else_=0,
                )
            ),
            0,
        ).label("accrued"),
        func.coalesce(
            func.sum(
                case(
                    (
                        col(TimeOffLedgerEntry.entry_type) == LedgerEntryType.USAGE.value,
                        func.abs(col(TimeOffLedgerEntry.amount_minutes)),
                    ),
                    else_=0,
                )
            ),
            0,
        ).label("used"),
        func.coalesce(
            func.sum(
                case(
                    (
                        col(TimeOffLedgerEntry.entry_type) == LedgerEntryType.HOLD.value,
                        func.abs(col(TimeOffLedgerEntry.amount_minutes)),
                    ),
                    (
                        col(TimeOffLedgerEntry.entry_type) == LedgerEntryType.HOLD_RELEASE.value,
                        -func.abs(col(TimeOffLedgerEntry.amount_minutes)),
                    ),
                    else_=0,
                )
            ),
            0,
        ).label("held"),
    ).where(*base_filter)

    result = await session.execute(query)
    row = result.one()
    return int(row.accrued), int(row.used), int(row.held)


async def _get_or_create_snapshot_for_update(
    session: AsyncSession,
    company_id: uuid.UUID,
    employee_id: uuid.UUID,
    policy_id: uuid.UUID,
) -> TimeOffBalanceSnapshot:
    """Get the balance snapshot with a FOR UPDATE lock, creating it if absent."""
    result = await session.execute(
        select(TimeOffBalanceSnapshot)
        .where(
            col(TimeOffBalanceSnapshot.company_id) == company_id,
            col(TimeOffBalanceSnapshot.employee_id) == employee_id,
            col(TimeOffBalanceSnapshot.policy_id) == policy_id,
        )
        .with_for_update()
    )
    snapshot = result.scalar_one_or_none()

    if snapshot is None:
        # First interaction — compute from any existing ledger entries.
        accrued, used, held = await _compute_balance_from_ledger(session, company_id, employee_id, policy_id)
        snapshot = TimeOffBalanceSnapshot(
            company_id=company_id,
            employee_id=employee_id,
            policy_id=policy_id,
            accrued_minutes=accrued,
            used_minutes=used,
            held_minutes=held,
            available_minutes=accrued - used - held,
            version=1,
        )
        session.add(snapshot)
        await session.flush()

    return snapshot


# ---------------------------------------------------------------------------
# Read path
# ---------------------------------------------------------------------------


async def get_employee_balances(
    session: AsyncSession,
    company_id: uuid.UUID,
    employee_id: uuid.UUID,
) -> BalanceListResponse:
    """Get all policy balances for an employee based on active assignments."""
    today = date.today()

    # Find all active assignments for this employee.
    assignments_result = await session.execute(
        select(TimeOffPolicyAssignment)
        .where(
            col(TimeOffPolicyAssignment.company_id) == company_id,
            col(TimeOffPolicyAssignment.employee_id) == employee_id,
            col(TimeOffPolicyAssignment.effective_from) <= today,
            or_(
                col(TimeOffPolicyAssignment.effective_to).is_(None),
                col(TimeOffPolicyAssignment.effective_to) > today,
            ),
        )
        .order_by(col(TimeOffPolicyAssignment.effective_from))
    )
    assignments = list(assignments_result.scalars().all())

    items: list[BalanceResponse] = []
    for assignment in assignments:
        # Fetch the policy for metadata.
        policy_result = await session.execute(
            select(TimeOffPolicy).where(col(TimeOffPolicy.id) == assignment.policy_id)
        )
        policy = policy_result.scalar_one()

        # Determine if unlimited from current version.
        current_version = await _get_current_version(session, assignment.policy_id)
        is_unlimited = False
        if current_version is not None:
            is_unlimited = current_version.type == PolicyType.UNLIMITED.value

        # Try to read snapshot; fall back to ledger computation.
        snapshot_result = await session.execute(
            select(TimeOffBalanceSnapshot).where(
                col(TimeOffBalanceSnapshot.company_id) == company_id,
                col(TimeOffBalanceSnapshot.employee_id) == employee_id,
                col(TimeOffBalanceSnapshot.policy_id) == assignment.policy_id,
            )
        )
        snapshot = snapshot_result.scalar_one_or_none()

        if snapshot is not None:
            accrued = snapshot.accrued_minutes
            used = snapshot.used_minutes
            held = snapshot.held_minutes
            available = snapshot.available_minutes
            updated_at = snapshot.updated_at
        else:
            accrued, used, held = await _compute_balance_from_ledger(
                session, company_id, employee_id, assignment.policy_id
            )
            available = accrued - used - held
            updated_at = None

        items.append(
            BalanceResponse(
                policy_id=assignment.policy_id,
                policy_key=policy.key,
                policy_category=policy.category,
                accrued_minutes=accrued,
                used_minutes=used,
                held_minutes=held,
                available_minutes=None if is_unlimited else available,
                is_unlimited=is_unlimited,
                updated_at=updated_at,
            )
        )

    return BalanceListResponse(items=items, total=len(items))


async def get_employee_ledger(
    session: AsyncSession,
    company_id: uuid.UUID,
    employee_id: uuid.UUID,
    policy_id: uuid.UUID,
    offset: int = 0,
    limit: int = 50,
) -> LedgerListResponse:
    """Get paginated ledger entries for an employee + policy."""
    base_filter = [
        col(TimeOffLedgerEntry.company_id) == company_id,
        col(TimeOffLedgerEntry.employee_id) == employee_id,
        col(TimeOffLedgerEntry.policy_id) == policy_id,
    ]

    count_result = await session.execute(select(func.count()).select_from(TimeOffLedgerEntry).where(*base_filter))
    total = count_result.scalar_one()

    entries_result = await session.execute(
        select(TimeOffLedgerEntry)
        .where(*base_filter)
        .order_by(
            col(TimeOffLedgerEntry.effective_at).desc(),
            col(TimeOffLedgerEntry.created_at).desc(),
        )
        .offset(offset)
        .limit(limit)
    )
    entries = list(entries_result.scalars().all())

    return LedgerListResponse(
        items=[_build_ledger_entry_response(e) for e in entries],
        total=total,
    )


# ---------------------------------------------------------------------------
# Write path — admin adjustments
# ---------------------------------------------------------------------------


async def create_adjustment(
    session: AsyncSession,
    auth: AuthContext,
    payload: CreateAdjustmentRequest,
) -> LedgerEntryResponse:
    """Create an admin balance adjustment.

    Flow:
    1. Verify active assignment for today
    2. Resolve current policy version
    3. Check if unlimited (skip balance validation for unlimited)
    4. Lock snapshot with SELECT FOR UPDATE
    5. If negative: enforce allow_negative + negative_limit_minutes
    6. Insert ADJUSTMENT ledger entry
    7. Update snapshot
    8. Write audit log
    9. Commit
    """
    today = date.today()

    # 1. Verify active assignment.
    await verify_active_assignment(session, auth.company_id, payload.employee_id, payload.policy_id, today)

    # 2. Resolve current policy version.
    current_version = await _get_current_version(session, payload.policy_id)
    if current_version is None:
        raise AppError("Policy has no active version", status_code=400)

    # 3. Determine if unlimited.
    settings = _settings_adapter.validate_python(current_version.settings_json or {})
    is_unlimited = settings.type == "UNLIMITED"

    # 4. Lock and get/create snapshot.
    snapshot = await _get_or_create_snapshot_for_update(
        session, auth.company_id, payload.employee_id, payload.policy_id
    )

    # 5. Negative balance enforcement (only for non-unlimited policies).
    if not is_unlimited and payload.amount_minutes < 0:
        new_available = snapshot.available_minutes + payload.amount_minutes
        allow_negative = getattr(settings, "allow_negative", False)
        negative_limit = getattr(settings, "negative_limit_minutes", None)

        if not allow_negative and new_available < 0:
            raise AppError("Insufficient balance for this adjustment", status_code=400)
        if allow_negative and negative_limit is not None and new_available < -negative_limit:
            raise AppError(
                f"Adjustment would exceed negative balance limit of {negative_limit} minutes",
                status_code=400,
            )

    # 6. Insert ledger entry.
    entry_id = uuid.uuid4()
    entry = TimeOffLedgerEntry(
        id=entry_id,
        company_id=auth.company_id,
        employee_id=payload.employee_id,
        policy_id=payload.policy_id,
        policy_version_id=current_version.id,
        entry_type=LedgerEntryType.ADJUSTMENT.value,
        amount_minutes=payload.amount_minutes,
        effective_at=datetime.now(UTC),
        source_type=LedgerSourceType.ADMIN.value,
        source_id=str(entry_id),
        metadata_json={"reason": payload.reason, "adjusted_by": str(auth.user_id)},
    )
    session.add(entry)

    # 7. Update snapshot.
    snapshot.accrued_minutes += payload.amount_minutes
    snapshot.available_minutes = snapshot.accrued_minutes - snapshot.used_minutes - snapshot.held_minutes
    snapshot.version += 1

    await session.flush()

    # 8. Write audit log.
    await write_audit_log(
        session,
        company_id=auth.company_id,
        actor_id=auth.user_id,
        entity_type=AuditEntityType.ADJUSTMENT,
        entity_id=entry.id,
        action=AuditAction.CREATE,
        after_json=model_to_audit_dict(entry),
    )

    # 9. Commit and return.
    await session.commit()
    await session.refresh(entry)
    return _build_ledger_entry_response(entry)
