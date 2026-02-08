"""Carryover and expiration processing engines.

Carryover: Runs on Jan 1 to process year-end balance carryover.
Expiration: Runs daily to process calendar-date and post-carryover expirations.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

from pydantic import TypeAdapter
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlmodel import col

from app.models.assignment import TimeOffPolicyAssignment
from app.models.enums import (
    AccrualMethod,
    AuditAction,
    AuditEntityType,
    LedgerEntryType,
    LedgerSourceType,
    PolicyType,
)
from app.models.ledger import TimeOffLedgerEntry
from app.models.policy import TimeOffPolicyVersion
from app.schemas.policy import (
    CarryoverSettings,
    ExpirationSettings,
    HoursWorkedAccrualSettings,
    PolicySettings,
    TimeAccrualSettings,
)
from app.services.audit import model_to_audit_dict, write_audit_log
from app.services.balance import _get_or_create_snapshot_for_update

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_settings_adapter: TypeAdapter[PolicySettings] = TypeAdapter(PolicySettings)

SYSTEM_ACTOR = uuid.UUID(int=0)


@dataclass
class CarryoverRunResult:
    """Result of a carryover processing run."""

    target_date: date
    carryovers_processed: int = 0
    expirations_processed: int = 0
    skipped: int = 0
    errors: int = 0
    details: list[dict[str, object]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _find_active_accrual_assignments(
    session: AsyncSession,
    target_date: date,
    company_id: uuid.UUID | None = None,
) -> list[Any]:
    """Find all active accrual assignments with their current policy version.

    Returns Row objects with company_id, employee_id, policy_id, version_id, settings_json.
    """
    filters = [
        col(TimeOffPolicyAssignment.effective_from) <= target_date,
        or_(
            col(TimeOffPolicyAssignment.effective_to).is_(None),
            col(TimeOffPolicyAssignment.effective_to) > target_date,
        ),
        col(TimeOffPolicyVersion.type) == PolicyType.ACCRUAL.value,
        col(TimeOffPolicyVersion.accrual_method).in_([AccrualMethod.TIME.value, AccrualMethod.HOURS_WORKED.value]),
    ]

    if company_id is not None:
        filters.append(col(TimeOffPolicyAssignment.company_id) == company_id)

    result = await session.execute(
        select(  # ty: ignore[no-matching-overload]
            TimeOffPolicyAssignment.company_id,
            TimeOffPolicyAssignment.employee_id,
            TimeOffPolicyAssignment.policy_id,
            col(TimeOffPolicyVersion.id).label("version_id"),
            col(TimeOffPolicyVersion.settings_json).label("settings_json"),
        )
        .join(
            TimeOffPolicyVersion,
            TimeOffPolicyAssignment.policy_id == TimeOffPolicyVersion.policy_id,
        )
        .where(*filters)
        .distinct()
    )
    return list(result.all())


async def _post_ledger_entry(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    employee_id: uuid.UUID,
    policy_id: uuid.UUID,
    policy_version_id: uuid.UUID,
    entry_type: LedgerEntryType,
    amount_minutes: int,
    effective_at: datetime,
    source_id: str,
    metadata_json: dict[str, object] | None = None,
) -> TimeOffLedgerEntry | None:
    """Post a ledger entry with idempotency. Returns None if duplicate."""
    entry = TimeOffLedgerEntry(
        company_id=company_id,
        employee_id=employee_id,
        policy_id=policy_id,
        policy_version_id=policy_version_id,
        entry_type=entry_type.value,
        amount_minutes=amount_minutes,
        effective_at=effective_at,
        source_type=LedgerSourceType.SYSTEM.value,
        source_id=source_id,
        metadata_json=metadata_json,
    )

    try:
        async with session.begin_nested():
            session.add(entry)
            await session.flush()
    except IntegrityError:
        return None  # Idempotent: already processed

    return entry


# ---------------------------------------------------------------------------
# Carryover processing
# ---------------------------------------------------------------------------


async def run_carryover_processing(
    session: AsyncSession,
    target_date: date | None = None,
    *,
    company_id: uuid.UUID | None = None,
) -> CarryoverRunResult:
    """Process year-end carryover for all active accrual assignments.

    Only runs for Jan 1 (processes the prior year's boundary). For each
    assignment with carryover.enabled:
    1. Lock the balance snapshot
    2. Compute available = accrued - used - held
    3. If cap: carry_amount = min(available, cap_minutes); else carry all
    4. expire_amount = available - carry_amount (excess expires)
    5. Post EXPIRATION entry if expire_amount > 0
    6. Post CARRYOVER marker (amount=0) with metadata
    7. Update snapshot, audit log

    Idempotent via (source_type, source_id, entry_type) unique constraint.
    """
    if target_date is None:
        target_date = date.today()

    result = CarryoverRunResult(target_date=target_date)

    # Only process on Jan 1 (or when explicitly triggered with a date)
    if target_date.month != 1 or target_date.day != 1:
        logger.info("Carryover skipped: target_date %s is not Jan 1", target_date)
        return result

    year = target_date.year - 1  # Process the prior year

    assignments = await _find_active_accrual_assignments(session, target_date, company_id)

    for row in assignments:
        cid, eid, pid, vid = row.company_id, row.employee_id, row.policy_id, row.version_id
        settings_json = row.settings_json

        try:
            settings = _settings_adapter.validate_python(settings_json or {})

            # Only process policies with carryover enabled
            carryover = _get_carryover_settings(settings)
            if carryover is None or not carryover.enabled:
                result.skipped += 1
                continue

            # Lock snapshot
            snapshot = await _get_or_create_snapshot_for_update(session, cid, eid, pid)

            # Compute available balance (held balance is protected)
            available = snapshot.accrued_minutes - snapshot.used_minutes - snapshot.held_minutes

            if available <= 0:
                result.skipped += 1
                continue

            # Determine carry and expire amounts
            cap = carryover.cap_minutes
            carry_amount = min(available, cap) if cap is not None else available

            expire_amount = available - carry_amount

            effective = datetime(target_date.year, 1, 1, 0, 0, 0, tzinfo=UTC)

            # Post EXPIRATION entry if there's excess to expire
            if expire_amount > 0:
                exp_source_id = f"carryover:{pid}:{eid}:{year}"
                exp_entry = await _post_ledger_entry(
                    session,
                    company_id=cid,
                    employee_id=eid,
                    policy_id=pid,
                    policy_version_id=vid,
                    entry_type=LedgerEntryType.EXPIRATION,
                    amount_minutes=-expire_amount,
                    effective_at=effective,
                    source_id=exp_source_id,
                    metadata_json={
                        "reason": "year_end_carryover_excess",
                        "year": year,
                        "expired_minutes": expire_amount,
                        "cap_minutes": cap,
                    },
                )

                if exp_entry is not None:
                    # Update snapshot for expiration
                    snapshot.accrued_minutes -= expire_amount
                    snapshot.available_minutes = (
                        snapshot.accrued_minutes - snapshot.used_minutes - snapshot.held_minutes
                    )
                    snapshot.version += 1

                    await write_audit_log(
                        session,
                        company_id=cid,
                        actor_id=SYSTEM_ACTOR,
                        entity_type=AuditEntityType.ACCRUAL,
                        entity_id=exp_entry.id,
                        action=AuditAction.CREATE,
                        after_json=model_to_audit_dict(exp_entry),
                    )

                    result.expirations_processed += 1

            # Post CARRYOVER marker (amount=0, metadata tracks what happened)
            marker_source_id = f"carryover_marker:{pid}:{eid}:{year}"
            marker_entry = await _post_ledger_entry(
                session,
                company_id=cid,
                employee_id=eid,
                policy_id=pid,
                policy_version_id=vid,
                entry_type=LedgerEntryType.CARRYOVER,
                amount_minutes=0,
                effective_at=effective,
                source_id=marker_source_id,
                metadata_json={
                    "year": year,
                    "carried_minutes": carry_amount,
                    "expired_minutes": expire_amount,
                    "cap_minutes": cap,
                    "expires_after_days": carryover.expires_after_days,
                },
            )

            if marker_entry is not None:
                await write_audit_log(
                    session,
                    company_id=cid,
                    actor_id=SYSTEM_ACTOR,
                    entity_type=AuditEntityType.ACCRUAL,
                    entity_id=marker_entry.id,
                    action=AuditAction.CREATE,
                    after_json=model_to_audit_dict(marker_entry),
                )
                result.carryovers_processed += 1
            else:
                result.skipped += 1  # Already processed (idempotent)

            await session.flush()

        except Exception:
            logger.exception("Carryover failed for employee=%s policy=%s", eid, pid)
            result.errors += 1

    await session.commit()
    return result


# ---------------------------------------------------------------------------
# Expiration processing
# ---------------------------------------------------------------------------


async def run_expiration_processing(
    session: AsyncSession,
    target_date: date | None = None,
    *,
    company_id: uuid.UUID | None = None,
) -> CarryoverRunResult:
    """Process balance expirations for all active accrual assignments.

    Two modes:
    1. Calendar-date expiration (expires_on_month/day): Fires when target_date
       matches the configured month/day. Expires entire available balance.
    2. Carryover expiration (carryover.expires_after_days): Fires N days after
       Jan 1. Finds the CARRYOVER marker and expires the carried amount.

    Idempotent via (source_type, source_id, entry_type) unique constraint.
    """
    if target_date is None:
        target_date = date.today()

    result = CarryoverRunResult(target_date=target_date)

    assignments = await _find_active_accrual_assignments(session, target_date, company_id)

    for row in assignments:
        cid, eid, pid, vid = row.company_id, row.employee_id, row.policy_id, row.version_id
        settings_json = row.settings_json

        try:
            settings = _settings_adapter.validate_python(settings_json or {})

            # Check calendar-date expiration
            expiration = _get_expiration_settings(settings)
            if (
                expiration is not None
                and expiration.enabled
                and expiration.expires_on_month is not None
                and expiration.expires_on_day is not None
                and target_date.month == expiration.expires_on_month
                and target_date.day == expiration.expires_on_day
            ):
                await _process_calendar_expiration(session, result, cid, eid, pid, vid, target_date)

            # Check carryover expiration (expires_after_days from Jan 1)
            carryover = _get_carryover_settings(settings)
            if carryover is not None and carryover.enabled and carryover.expires_after_days is not None:
                expiry_date = date(target_date.year, 1, 1) + timedelta(days=carryover.expires_after_days)
                if target_date == expiry_date:
                    await _process_carryover_expiration(
                        session, result, cid, eid, pid, vid, target_date, target_date.year - 1
                    )

        except Exception:
            logger.exception("Expiration failed for employee=%s policy=%s", eid, pid)
            result.errors += 1

    await session.commit()
    return result


async def _process_calendar_expiration(
    session: AsyncSession,
    result: CarryoverRunResult,
    company_id: uuid.UUID,
    employee_id: uuid.UUID,
    policy_id: uuid.UUID,
    version_id: uuid.UUID,
    target_date: date,
) -> None:
    """Expire entire available balance on a configured calendar date."""
    snapshot = await _get_or_create_snapshot_for_update(session, company_id, employee_id, policy_id)

    available = snapshot.accrued_minutes - snapshot.used_minutes - snapshot.held_minutes
    if available <= 0:
        result.skipped += 1
        return

    source_id = f"expiration:{policy_id}:{employee_id}:{target_date.year}:{target_date.month:02d}-{target_date.day:02d}"
    effective = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=UTC)

    entry = await _post_ledger_entry(
        session,
        company_id=company_id,
        employee_id=employee_id,
        policy_id=policy_id,
        policy_version_id=version_id,
        entry_type=LedgerEntryType.EXPIRATION,
        amount_minutes=-available,
        effective_at=effective,
        source_id=source_id,
        metadata_json={
            "reason": "calendar_date_expiration",
            "expired_minutes": available,
            "expires_on": f"{target_date.month:02d}-{target_date.day:02d}",
        },
    )

    if entry is not None:
        snapshot.accrued_minutes -= available
        snapshot.available_minutes = snapshot.accrued_minutes - snapshot.used_minutes - snapshot.held_minutes
        snapshot.version += 1

        await write_audit_log(
            session,
            company_id=company_id,
            actor_id=SYSTEM_ACTOR,
            entity_type=AuditEntityType.ACCRUAL,
            entity_id=entry.id,
            action=AuditAction.CREATE,
            after_json=model_to_audit_dict(entry),
        )
        result.expirations_processed += 1
        await session.flush()
    else:
        result.skipped += 1


async def _process_carryover_expiration(
    session: AsyncSession,
    result: CarryoverRunResult,
    company_id: uuid.UUID,
    employee_id: uuid.UUID,
    policy_id: uuid.UUID,
    version_id: uuid.UUID,
    target_date: date,
    carryover_year: int,
) -> None:
    """Expire carried-over balance N days after Jan 1."""
    # Find the CARRYOVER marker from the prior year-end
    marker_source_id = f"carryover_marker:{policy_id}:{employee_id}:{carryover_year}"
    marker_result = await session.execute(
        select(TimeOffLedgerEntry).where(
            col(TimeOffLedgerEntry.source_id) == marker_source_id,
            col(TimeOffLedgerEntry.entry_type) == LedgerEntryType.CARRYOVER.value,
        )
    )
    marker = marker_result.scalar_one_or_none()

    if marker is None or marker.metadata_json is None:
        result.skipped += 1
        return

    carried_minutes = marker.metadata_json.get("carried_minutes", 0)
    if carried_minutes <= 0:
        result.skipped += 1
        return

    # Lock snapshot and expire the carried amount (but not more than available)
    snapshot = await _get_or_create_snapshot_for_update(session, company_id, employee_id, policy_id)
    available = snapshot.accrued_minutes - snapshot.used_minutes - snapshot.held_minutes
    expire_amount = min(carried_minutes, max(available, 0))

    if expire_amount <= 0:
        result.skipped += 1
        return

    source_id = f"carryover_expiry:{policy_id}:{employee_id}:{carryover_year}"
    effective = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=UTC)

    entry = await _post_ledger_entry(
        session,
        company_id=company_id,
        employee_id=employee_id,
        policy_id=policy_id,
        policy_version_id=version_id,
        entry_type=LedgerEntryType.EXPIRATION,
        amount_minutes=-expire_amount,
        effective_at=effective,
        source_id=source_id,
        metadata_json={
            "reason": "carryover_expiration",
            "carryover_year": carryover_year,
            "carried_minutes": carried_minutes,
            "expired_minutes": expire_amount,
        },
    )

    if entry is not None:
        snapshot.accrued_minutes -= expire_amount
        snapshot.available_minutes = snapshot.accrued_minutes - snapshot.used_minutes - snapshot.held_minutes
        snapshot.version += 1

        await write_audit_log(
            session,
            company_id=company_id,
            actor_id=SYSTEM_ACTOR,
            entity_type=AuditEntityType.ACCRUAL,
            entity_id=entry.id,
            action=AuditAction.CREATE,
            after_json=model_to_audit_dict(entry),
        )
        result.expirations_processed += 1
        await session.flush()
    else:
        result.skipped += 1


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------


def _get_carryover_settings(settings: PolicySettings) -> CarryoverSettings | None:
    """Extract carryover settings from policy settings, if applicable."""
    if isinstance(settings, (TimeAccrualSettings, HoursWorkedAccrualSettings)):
        return settings.carryover
    return None


def _get_expiration_settings(settings: PolicySettings) -> ExpirationSettings | None:
    """Extract expiration settings from policy settings, if applicable."""
    if isinstance(settings, (TimeAccrualSettings, HoursWorkedAccrualSettings)):
        return settings.expiration
    return None
