"""Accrual engine: time-based (scheduled) and hours-worked (payroll-driven) accrual processing."""

from __future__ import annotations

import logging
import uuid
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

from pydantic import TypeAdapter
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlmodel import col

from app.models.assignment import TimeOffPolicyAssignment
from app.models.enums import (
    AccrualFrequency,
    AccrualMethod,
    AccrualTiming,
    AuditAction,
    AuditEntityType,
    LedgerEntryType,
    LedgerSourceType,
    PolicyType,
    ProrationMethod,
)
from app.models.ledger import TimeOffLedgerEntry
from app.models.policy import TimeOffPolicyVersion
from app.schemas.policy import (
    HoursWorkedAccrualSettings,
    PolicySettings,
    TimeAccrualSettings,
)
from app.services.audit import model_to_audit_dict, write_audit_log
from app.services.balance import _get_or_create_snapshot_for_update
from app.services.employee import get_employee_service
from app.services.policy import get_version_effective_on

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas.accrual import PayrollProcessedPayload

logger = logging.getLogger(__name__)

_settings_adapter: TypeAdapter[PolicySettings] = TypeAdapter(PolicySettings)

# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class AccrualRunResult:
    """Summary of a time-based accrual run."""

    target_date: date
    processed: int = 0
    accrued: int = 0
    skipped: int = 0
    errors: int = 0


@dataclass
class PayrollProcessingResult:
    """Summary of a payroll webhook processing."""

    payroll_run_id: str
    processed: int = 0
    accrued: int = 0
    skipped: int = 0
    errors: int = 0


# ---------------------------------------------------------------------------
# Pure computation helpers (no DB)
# ---------------------------------------------------------------------------


def _get_period_boundaries(
    frequency: AccrualFrequency,
    target_date: date,
) -> tuple[date, date]:
    """Return (period_start, period_end) as half-open interval [start, end).

    DAILY:   [target_date, target_date + 1 day)
    MONTHLY: [1st of month, 1st of next month)
    YEARLY:  [Jan 1, Jan 1 next year)
    """
    if frequency == AccrualFrequency.DAILY:
        return target_date, target_date + timedelta(days=1)

    if frequency == AccrualFrequency.MONTHLY:
        period_start = target_date.replace(day=1)
        _, days_in_month = monthrange(target_date.year, target_date.month)
        period_end = period_start + timedelta(days=days_in_month)
        return period_start, period_end

    # YEARLY
    period_start = date(target_date.year, 1, 1)
    period_end = date(target_date.year + 1, 1, 1)
    return period_start, period_end


def _is_accrual_date(
    frequency: AccrualFrequency,
    timing: AccrualTiming,
    target_date: date,
) -> bool:
    """Determine if an accrual should be posted on target_date."""
    if frequency == AccrualFrequency.DAILY:
        return True

    if frequency == AccrualFrequency.MONTHLY:
        if timing == AccrualTiming.START_OF_PERIOD:
            return target_date.day == 1
        # END_OF_PERIOD: last day of month
        _, days_in_month = monthrange(target_date.year, target_date.month)
        return target_date.day == days_in_month

    # YEARLY
    if timing == AccrualTiming.START_OF_PERIOD:
        return target_date.month == 1 and target_date.day == 1
    # END_OF_PERIOD
    return target_date.month == 12 and target_date.day == 31


def _resolve_accrual_rate(
    settings: TimeAccrualSettings,
    hire_date: date | None,
    assignment_from: date,
    target_date: date,
) -> int:
    """Resolve the accrual rate considering tenure tiers.

    If tenure tiers are defined and a matching tier is found, returns
    the tier's accrual_rate_minutes. Otherwise returns the base rate
    from the policy settings.
    """
    # Determine base rate from frequency
    base_rate: int | None = None
    if settings.accrual_frequency == AccrualFrequency.DAILY:
        base_rate = settings.rate_minutes_per_day
    elif settings.accrual_frequency == AccrualFrequency.MONTHLY:
        base_rate = settings.rate_minutes_per_month
    elif settings.accrual_frequency == AccrualFrequency.YEARLY:
        base_rate = settings.rate_minutes_per_year

    if base_rate is None:
        return 0

    # Check tenure tiers
    if not settings.tenure_tiers:
        return base_rate

    start = hire_date or assignment_from
    months = (target_date.year - start.year) * 12 + (target_date.month - start.month)

    # Sort tiers by min_months descending; first match wins (highest tier)
    sorted_tiers = sorted(settings.tenure_tiers, key=lambda t: t.min_months, reverse=True)
    for tier in sorted_tiers:
        if months >= tier.min_months:
            return tier.accrual_rate_minutes

    return base_rate


def _compute_accrual_amount(
    settings: TimeAccrualSettings,
    target_date: date,
    assignment_effective_from: date,
    hire_date: date | None = None,
) -> int:
    """Compute the accrual amount in minutes for a single period.

    Handles proration for mid-period joins and tenure tier overrides.
    All arithmetic uses integers to avoid float drift.
    """
    rate = _resolve_accrual_rate(settings, hire_date, assignment_effective_from, target_date)
    if rate <= 0:
        return 0

    # For NONE proration, always return the full rate
    if settings.proration == ProrationMethod.NONE:
        return rate

    # DAYS_ACTIVE proration
    period_start, period_end = _get_period_boundaries(settings.accrual_frequency, target_date)
    total_days = (period_end - period_start).days
    if total_days <= 0:
        return 0

    # The assignment might have started mid-period
    active_start = max(assignment_effective_from, period_start)
    active_days = (period_end - active_start).days

    if active_days >= total_days:
        return rate  # Full period, no proration needed

    if active_days <= 0:
        return 0

    return (rate * active_days) // total_days


def _apply_bank_cap(
    current_accrued: int,
    accrual_amount: int,
    bank_cap_minutes: int | None,
) -> int:
    """Clamp accrual_amount so total accrued does not exceed bank_cap_minutes.

    Returns the clamped amount (could be 0 if already at/above cap).
    """
    if bank_cap_minutes is None:
        return accrual_amount

    headroom = bank_cap_minutes - current_accrued
    if headroom <= 0:
        return 0

    return min(accrual_amount, headroom)


def _compute_hours_worked_accrual(
    settings: HoursWorkedAccrualSettings,
    worked_minutes: int,
) -> int:
    """Compute accrual from hours-worked ratio using integer arithmetic.

    Formula: (worked_minutes * accrue_minutes) // per_worked_minutes
    """
    ratio = settings.accrual_ratio
    return (worked_minutes * ratio.accrue_minutes) // ratio.per_worked_minutes


def _build_time_accrual_source_id(
    policy_id: uuid.UUID,
    employee_id: uuid.UUID,
    target_date: date,
) -> str:
    """Build idempotency source_id for a time-based accrual."""
    return f"accrual:{policy_id}:{employee_id}:{target_date.isoformat()}"


def _build_payroll_source_id(
    payroll_run_id: str,
    employee_id: uuid.UUID,
    policy_id: uuid.UUID,
) -> str:
    """Build idempotency source_id for a payroll-driven accrual."""
    return f"payroll:{payroll_run_id}:{employee_id}:{policy_id}"


# ---------------------------------------------------------------------------
# DB-backed helpers
# ---------------------------------------------------------------------------


@dataclass
class _AssignmentInfo:
    """Lightweight carrier for assignment + policy metadata."""

    company_id: uuid.UUID
    employee_id: uuid.UUID
    policy_id: uuid.UUID
    assignment_id: uuid.UUID
    effective_from: date
    effective_to: date | None = None
    policy_version_id: uuid.UUID = field(default_factory=uuid.uuid4)


async def _find_active_time_assignments(
    session: AsyncSession,
    target_date: date,
    *,
    company_id: uuid.UUID | None = None,
) -> list[_AssignmentInfo]:
    """Find all active assignments where the policy version is TIME accrual.

    Joins assignments with policy versions to filter for TIME accrual policies
    that are active (version effective) on the target date.
    """
    filters = [
        col(TimeOffPolicyAssignment.effective_from) <= target_date,
        or_(
            col(TimeOffPolicyAssignment.effective_to).is_(None),
            col(TimeOffPolicyAssignment.effective_to) > target_date,
        ),
        col(TimeOffPolicyVersion.effective_from) <= target_date,
        or_(
            col(TimeOffPolicyVersion.effective_to).is_(None),
            col(TimeOffPolicyVersion.effective_to) > target_date,
        ),
        col(TimeOffPolicyVersion.type) == PolicyType.ACCRUAL.value,
        col(TimeOffPolicyVersion.accrual_method) == AccrualMethod.TIME.value,
    ]

    if company_id is not None:
        filters.append(col(TimeOffPolicyAssignment.company_id) == company_id)

    result = await session.execute(
        select(  # type: ignore[call-overload]
            TimeOffPolicyAssignment.company_id,
            TimeOffPolicyAssignment.employee_id,
            TimeOffPolicyAssignment.policy_id,
            TimeOffPolicyAssignment.id,
            TimeOffPolicyAssignment.effective_from,
            TimeOffPolicyAssignment.effective_to,
            col(TimeOffPolicyVersion.id).label("version_id"),
        )
        .join(
            TimeOffPolicyVersion,
            TimeOffPolicyAssignment.policy_id == TimeOffPolicyVersion.policy_id,
        )
        .where(*filters)
    )

    return [
        _AssignmentInfo(
            company_id=row.company_id,
            employee_id=row.employee_id,
            policy_id=row.policy_id,
            assignment_id=row.id,
            effective_from=row.effective_from,
            effective_to=row.effective_to,
            policy_version_id=row.version_id,
        )
        for row in result.all()
    ]


async def _find_hours_worked_assignments(
    session: AsyncSession,
    company_id: uuid.UUID,
    employee_id: uuid.UUID,
    target_date: date,
) -> list[_AssignmentInfo]:
    """Find active HOURS_WORKED assignments for one employee."""
    result = await session.execute(
        select(  # type: ignore[call-overload]
            TimeOffPolicyAssignment.company_id,
            TimeOffPolicyAssignment.employee_id,
            TimeOffPolicyAssignment.policy_id,
            TimeOffPolicyAssignment.id,
            TimeOffPolicyAssignment.effective_from,
            TimeOffPolicyAssignment.effective_to,
            col(TimeOffPolicyVersion.id).label("version_id"),
        )
        .join(
            TimeOffPolicyVersion,
            TimeOffPolicyAssignment.policy_id == TimeOffPolicyVersion.policy_id,
        )
        .where(
            col(TimeOffPolicyAssignment.company_id) == company_id,
            col(TimeOffPolicyAssignment.employee_id) == employee_id,
            col(TimeOffPolicyAssignment.effective_from) <= target_date,
            or_(
                col(TimeOffPolicyAssignment.effective_to).is_(None),
                col(TimeOffPolicyAssignment.effective_to) > target_date,
            ),
            col(TimeOffPolicyVersion.effective_from) <= target_date,
            or_(
                col(TimeOffPolicyVersion.effective_to).is_(None),
                col(TimeOffPolicyVersion.effective_to) > target_date,
            ),
            col(TimeOffPolicyVersion.type) == PolicyType.ACCRUAL.value,
            col(TimeOffPolicyVersion.accrual_method) == AccrualMethod.HOURS_WORKED.value,
        )
    )

    return [
        _AssignmentInfo(
            company_id=row.company_id,
            employee_id=row.employee_id,
            policy_id=row.policy_id,
            assignment_id=row.id,
            effective_from=row.effective_from,
            effective_to=row.effective_to,
            policy_version_id=row.version_id,
        )
        for row in result.all()
    ]


async def _post_accrual_entry(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    employee_id: uuid.UUID,
    policy_id: uuid.UUID,
    policy_version_id: uuid.UUID,
    amount_minutes: int,
    effective_at: datetime,
    source_type: LedgerSourceType,
    source_id: str,
    metadata_json: dict[str, object] | None = None,
) -> TimeOffLedgerEntry | None:
    """Post a single ACCRUAL ledger entry, updating the snapshot.

    Locks the snapshot with SELECT FOR UPDATE, applies bank cap,
    inserts the ledger entry, and updates the snapshot.

    Returns the entry on success, or None if skipped (duplicate/zero amount).
    Catches IntegrityError for idempotent duplicate detection.
    """
    # Resolve settings to check bank cap
    target = effective_at.date() if effective_at.tzinfo is not None else date.today()
    version = await get_version_effective_on(session, policy_id, target)
    bank_cap_minutes: int | None = None
    if version is not None:
        settings = _settings_adapter.validate_python(version.settings_json or {})
        bank_cap_minutes = getattr(settings, "bank_cap_minutes", None)

    # Lock snapshot
    snapshot = await _get_or_create_snapshot_for_update(session, company_id, employee_id, policy_id)

    # Apply bank cap
    capped_amount = _apply_bank_cap(snapshot.accrued_minutes, amount_minutes, bank_cap_minutes)
    if capped_amount <= 0:
        return None

    # Insert ledger entry inside a savepoint so that a duplicate IntegrityError
    # only rolls back this insert, not the outer transaction.
    entry = TimeOffLedgerEntry(
        company_id=company_id,
        employee_id=employee_id,
        policy_id=policy_id,
        policy_version_id=policy_version_id,
        entry_type=LedgerEntryType.ACCRUAL.value,
        amount_minutes=capped_amount,
        effective_at=effective_at,
        source_type=source_type.value,
        source_id=source_id,
        metadata_json=metadata_json,
    )

    try:
        async with session.begin_nested():
            session.add(entry)
            await session.flush()
    except IntegrityError:
        return None  # Idempotent: already processed

    # Update snapshot
    snapshot.accrued_minutes += capped_amount
    snapshot.available_minutes = snapshot.accrued_minutes - snapshot.used_minutes - snapshot.held_minutes
    snapshot.version += 1

    await session.flush()

    # Audit
    await write_audit_log(
        session,
        company_id=company_id,
        actor_id=uuid.UUID(int=0),  # SYSTEM actor
        entity_type=AuditEntityType.ACCRUAL,
        entity_id=entry.id,
        action=AuditAction.CREATE,
        after_json=model_to_audit_dict(entry),
    )

    return entry


# ---------------------------------------------------------------------------
# Time-based accrual orchestration
# ---------------------------------------------------------------------------


async def run_time_based_accruals(
    session: AsyncSession,
    target_date: date | None = None,
    *,
    company_id: uuid.UUID | None = None,
) -> AccrualRunResult:
    """Run time-based accruals for all active assignments on the target date.

    Finds all active TIME accrual assignments and posts ACCRUAL ledger entries
    for each. The function is idempotent: re-running for the same date will
    not create duplicate entries.

    Args:
        session: Database session (caller is responsible for commit).
        target_date: Date to run accruals for (defaults to today).
        company_id: If provided, only process assignments for this company.
    """
    if target_date is None:
        target_date = date.today()

    result = AccrualRunResult(target_date=target_date)

    # Find all active TIME assignments
    assignments = await _find_active_time_assignments(session, target_date, company_id=company_id)

    employee_service = get_employee_service()

    for info in assignments:
        result.processed += 1
        try:
            # Resolve the policy version effective on this date
            version = await get_version_effective_on(session, info.policy_id, target_date)
            if version is None:
                result.skipped += 1
                continue

            settings = _settings_adapter.validate_python(version.settings_json or {})
            if not isinstance(settings, TimeAccrualSettings):
                result.skipped += 1
                continue

            # Check if this is an accrual date
            if not _is_accrual_date(settings.accrual_frequency, settings.accrual_timing, target_date):
                result.skipped += 1
                continue

            # Resolve hire_date for tenure tiers
            hire_date: date | None = None
            employee = await employee_service.get_employee(info.company_id, info.employee_id)
            if employee is not None:
                hire_date = employee.hire_date

            # Compute accrual amount
            amount = _compute_accrual_amount(settings, target_date, info.effective_from, hire_date)
            if amount <= 0:
                result.skipped += 1
                continue

            # Build idempotency key
            source_id = _build_time_accrual_source_id(info.policy_id, info.employee_id, target_date)

            # Post the accrual entry
            entry = await _post_accrual_entry(
                session,
                company_id=info.company_id,
                employee_id=info.employee_id,
                policy_id=info.policy_id,
                policy_version_id=version.id,
                amount_minutes=amount,
                effective_at=datetime(target_date.year, target_date.month, target_date.day, tzinfo=UTC),
                source_type=LedgerSourceType.SYSTEM,
                source_id=source_id,
                metadata_json={
                    "accrual_frequency": settings.accrual_frequency.value,
                    "accrual_timing": settings.accrual_timing.value,
                    "computed_amount": amount,
                },
            )

            if entry is not None:
                result.accrued += 1
            else:
                result.skipped += 1

        except Exception:
            logger.exception(
                "Error processing time accrual for employee=%s policy=%s",
                info.employee_id,
                info.policy_id,
            )
            result.errors += 1

    await session.commit()
    return result


# ---------------------------------------------------------------------------
# Hours-worked / payroll accrual orchestration
# ---------------------------------------------------------------------------


async def process_payroll_event(
    session: AsyncSession,
    payload: PayrollProcessedPayload,
) -> PayrollProcessingResult:
    """Process an entire payroll webhook event.

    For each employee in the payload, finds active HOURS_WORKED assignments
    and posts ACCRUAL entries proportional to hours worked.

    Idempotent: replaying the same payroll_run_id produces no duplicates.
    """
    from datetime import UTC, datetime

    result = PayrollProcessingResult(payroll_run_id=payload.payroll_run_id)

    for employee_entry in payload.entries:
        # Find active HOURS_WORKED assignments for this employee
        assignments = await _find_hours_worked_assignments(
            session,
            payload.company_id,
            employee_entry.employee_id,
            payload.period_end,
        )

        for info in assignments:
            result.processed += 1
            try:
                # Resolve policy version
                version = await get_version_effective_on(session, info.policy_id, payload.period_end)
                if version is None:
                    result.skipped += 1
                    continue

                settings = _settings_adapter.validate_python(version.settings_json or {})
                if not isinstance(settings, HoursWorkedAccrualSettings):
                    result.skipped += 1
                    continue

                # Compute accrual
                amount = _compute_hours_worked_accrual(settings, employee_entry.worked_minutes)
                if amount <= 0:
                    result.skipped += 1
                    continue

                # Build idempotency key
                source_id = _build_payroll_source_id(
                    payload.payroll_run_id,
                    employee_entry.employee_id,
                    info.policy_id,
                )

                # Post the accrual entry
                entry = await _post_accrual_entry(
                    session,
                    company_id=payload.company_id,
                    employee_id=employee_entry.employee_id,
                    policy_id=info.policy_id,
                    policy_version_id=version.id,
                    amount_minutes=amount,
                    effective_at=datetime(
                        payload.period_end.year,
                        payload.period_end.month,
                        payload.period_end.day,
                        tzinfo=UTC,
                    ),
                    source_type=LedgerSourceType.PAYROLL,
                    source_id=source_id,
                    metadata_json={
                        "payroll_run_id": payload.payroll_run_id,
                        "worked_minutes": employee_entry.worked_minutes,
                        "computed_amount": amount,
                    },
                )

                if entry is not None:
                    result.accrued += 1
                else:
                    result.skipped += 1

            except Exception:
                logger.exception(
                    "Error processing payroll accrual for employee=%s policy=%s run=%s",
                    employee_entry.employee_id,
                    info.policy_id,
                    payload.payroll_run_id,
                )
                result.errors += 1

    await session.commit()
    return result
