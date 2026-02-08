# ruff: noqa: TC003
from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from pydantic import TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlmodel import col

from app.exceptions import AppError
from app.models.enums import (
    AuditAction,
    AuditEntityType,
    LedgerEntryType,
    LedgerSourceType,
    RequestStatus,
)
from app.models.ledger import TimeOffLedgerEntry
from app.models.request import TimeOffRequest
from app.schemas.policy import PolicySettings
from app.schemas.request import RequestListResponse, RequestResponse
from app.services.assignment import verify_active_assignment
from app.services.audit import model_to_audit_dict, write_audit_log
from app.services.balance import _get_or_create_snapshot_for_update
from app.services.duration import calculate_requested_minutes, localize_request_times
from app.services.policy import _get_current_version

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas.auth import AuthContext
    from app.schemas.request import DecisionPayload, SubmitRequestPayload

_settings_adapter: TypeAdapter[PolicySettings] = TypeAdapter(PolicySettings)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_request_response(request: TimeOffRequest) -> RequestResponse:
    """Map a request model to its response schema."""
    return RequestResponse(
        id=request.id,
        company_id=request.company_id,
        employee_id=request.employee_id,
        policy_id=request.policy_id,
        start_at=request.start_at,
        end_at=request.end_at,
        requested_minutes=request.requested_minutes,
        reason=request.reason,
        status=RequestStatus(request.status),
        submitted_at=request.submitted_at,
        decided_at=request.decided_at,
        decided_by=request.decided_by,
        decision_note=request.decision_note,
        idempotency_key=request.idempotency_key,
        created_at=request.created_at,
    )


async def _get_request_or_404(
    session: AsyncSession,
    company_id: uuid.UUID,
    request_id: uuid.UUID,
) -> TimeOffRequest:
    """Fetch a request by ID scoped to company. Raises 404 if not found."""
    result = await session.execute(
        select(TimeOffRequest).where(
            col(TimeOffRequest.id) == request_id,
            col(TimeOffRequest.company_id) == company_id,
        )
    )
    request = result.scalar_one_or_none()
    if request is None:
        raise AppError("Request not found", status_code=404)
    return request


async def _check_request_overlap(
    session: AsyncSession,
    company_id: uuid.UUID,
    employee_id: uuid.UUID,
    policy_id: uuid.UUID,
    start_at: datetime,
    end_at: datetime,
    exclude_request_id: uuid.UUID | None = None,
) -> None:
    """Raise 409 if an active request overlaps the given time range.

    Active means status is SUBMITTED or APPROVED. Two intervals overlap
    when existing.start_at < new.end_at AND existing.end_at > new.start_at.
    """
    active_statuses = [RequestStatus.SUBMITTED.value, RequestStatus.APPROVED.value]
    query = select(TimeOffRequest).where(
        col(TimeOffRequest.company_id) == company_id,
        col(TimeOffRequest.employee_id) == employee_id,
        col(TimeOffRequest.policy_id) == policy_id,
        col(TimeOffRequest.status).in_(active_statuses),
        col(TimeOffRequest.start_at) < end_at,
        col(TimeOffRequest.end_at) > start_at,
    )
    if exclude_request_id is not None:
        query = query.where(col(TimeOffRequest.id) != exclude_request_id)

    result = await session.execute(query)
    if result.scalar_one_or_none() is not None:
        raise AppError(
            "Request overlaps with an existing submitted or approved request",
            status_code=409,
        )


async def _release_hold(
    session: AsyncSession,
    request: TimeOffRequest,
    auth: AuthContext,
    new_status: RequestStatus,
    audit_action: AuditAction,
    decision_note: str | None = None,
) -> RequestResponse:
    """Shared logic for deny and cancel: release the HOLD and update status.

    1. Resolve current policy version.
    2. Lock snapshot.
    3. Insert HOLD_RELEASE entry.
    4. Update snapshot (held decreases, available increases).
    5. Update request status.
    6. Audit log.
    7. Commit and return.
    """
    current_version = await _get_current_version(session, request.policy_id)
    if current_version is None:
        raise AppError("Policy has no active version", status_code=400)

    snapshot = await _get_or_create_snapshot_for_update(
        session, auth.company_id, request.employee_id, request.policy_id
    )

    before_dict = model_to_audit_dict(request)

    now = datetime.now(UTC)

    # Insert HOLD_RELEASE: positive amount (credit, releases hold).
    hold_release = TimeOffLedgerEntry(
        company_id=auth.company_id,
        employee_id=request.employee_id,
        policy_id=request.policy_id,
        policy_version_id=current_version.id,
        entry_type=LedgerEntryType.HOLD_RELEASE.value,
        amount_minutes=request.requested_minutes,
        effective_at=now,
        source_type=LedgerSourceType.REQUEST.value,
        source_id=str(request.id),
    )
    session.add(hold_release)

    # Update snapshot: held decreases, available increases.
    snapshot.held_minutes -= request.requested_minutes
    snapshot.available_minutes = snapshot.accrued_minutes - snapshot.used_minutes - snapshot.held_minutes
    snapshot.version += 1

    # Update request.
    request.status = new_status.value
    request.decided_at = now
    request.decided_by = auth.user_id
    request.decision_note = decision_note

    await session.flush()

    await write_audit_log(
        session,
        company_id=auth.company_id,
        actor_id=auth.user_id,
        entity_type=AuditEntityType.REQUEST,
        entity_id=request.id,
        action=audit_action,
        before_json=before_dict,
        after_json=model_to_audit_dict(request),
    )

    await session.commit()
    await session.refresh(request)
    return _build_request_response(request)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def submit_request(
    session: AsyncSession,
    auth: AuthContext,
    payload: SubmitRequestPayload,
) -> RequestResponse:
    """Submit a time-off request, creating a balance HOLD.

    Flow:
    1. Verify active assignment for today
    2. Resolve current policy version
    3. Calculate request duration (schedule + holidays)
    4. Check for overlapping requests
    5. Parse policy settings for balance rules
    6. Lock snapshot with SELECT FOR UPDATE
    7. Enforce balance invariant (non-unlimited only)
    8. Create request record (SUBMITTED)
    9. Insert HOLD ledger entry (-minutes)
    10. Update snapshot (held +=, available -=)
    11. Write audit log
    12. Commit
    """
    today = date.today()

    # 0. Localize naive datetimes to the employee's timezone.
    #    The frontend sends naive strings from datetime-local inputs; they
    #    represent the employee's local schedule, not the submitter's browser TZ.
    start_at, end_at = await localize_request_times(
        session, auth.company_id, payload.employee_id, payload.start_at, payload.end_at
    )

    # 1. Verify active assignment.
    await verify_active_assignment(session, auth.company_id, payload.employee_id, payload.policy_id, today)

    # 2. Resolve current policy version.
    current_version = await _get_current_version(session, payload.policy_id)
    if current_version is None:
        raise AppError("Policy has no active version", status_code=400)

    # 3. Calculate duration.
    requested_minutes = await calculate_requested_minutes(
        session, auth.company_id, payload.employee_id, start_at, end_at
    )

    # 4. Check for overlapping requests.
    await _check_request_overlap(session, auth.company_id, payload.employee_id, payload.policy_id, start_at, end_at)

    # 5. Parse policy settings.
    settings = _settings_adapter.validate_python(current_version.settings_json or {})
    is_unlimited = settings.type == "UNLIMITED"

    # 6. Lock snapshot.
    snapshot = await _get_or_create_snapshot_for_update(
        session, auth.company_id, payload.employee_id, payload.policy_id
    )

    # 7. Balance check (non-unlimited only).
    if not is_unlimited:
        new_available = snapshot.available_minutes - requested_minutes
        allow_negative = getattr(settings, "allow_negative", False)
        negative_limit = getattr(settings, "negative_limit_minutes", None)

        if not allow_negative and new_available < 0:
            raise AppError("Insufficient balance for this request", status_code=400)
        if allow_negative and negative_limit is not None and new_available < -negative_limit:
            raise AppError(
                f"Request would exceed negative balance limit of {negative_limit} minutes",
                status_code=400,
            )

    # 8. Create request.
    now = datetime.now(UTC)
    time_off_request = TimeOffRequest(
        company_id=auth.company_id,
        employee_id=payload.employee_id,
        policy_id=payload.policy_id,
        start_at=start_at,
        end_at=end_at,
        requested_minutes=requested_minutes,
        reason=payload.reason,
        status=RequestStatus.SUBMITTED.value,
        submitted_at=now,
        idempotency_key=payload.idempotency_key,
    )
    session.add(time_off_request)

    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        # Idempotency: if the key already exists, return the existing request.
        if payload.idempotency_key is not None:
            result = await session.execute(
                select(TimeOffRequest).where(
                    col(TimeOffRequest.company_id) == auth.company_id,
                    col(TimeOffRequest.employee_id) == payload.employee_id,
                    col(TimeOffRequest.idempotency_key) == payload.idempotency_key,
                )
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                return _build_request_response(existing)
        raise AppError("Duplicate request", status_code=409) from None

    # 9. Insert HOLD ledger entry.
    hold_entry = TimeOffLedgerEntry(
        company_id=auth.company_id,
        employee_id=payload.employee_id,
        policy_id=payload.policy_id,
        policy_version_id=current_version.id,
        entry_type=LedgerEntryType.HOLD.value,
        amount_minutes=-requested_minutes,
        effective_at=now,
        source_type=LedgerSourceType.REQUEST.value,
        source_id=str(time_off_request.id),
    )
    session.add(hold_entry)

    # 10. Update snapshot.
    snapshot.held_minutes += requested_minutes
    snapshot.available_minutes = snapshot.accrued_minutes - snapshot.used_minutes - snapshot.held_minutes
    snapshot.version += 1

    await session.flush()

    # 11. Audit log.
    await write_audit_log(
        session,
        company_id=auth.company_id,
        actor_id=auth.user_id,
        entity_type=AuditEntityType.REQUEST,
        entity_id=time_off_request.id,
        action=AuditAction.SUBMIT,
        after_json=model_to_audit_dict(time_off_request),
    )

    # 12. Commit.
    await session.commit()
    await session.refresh(time_off_request)
    return _build_request_response(time_off_request)


async def approve_request(
    session: AsyncSession,
    auth: AuthContext,
    request_id: uuid.UUID,
    payload: DecisionPayload | None = None,
) -> RequestResponse:
    """Approve a submitted request: convert HOLD to USAGE.

    1. Fetch and validate request (must be SUBMITTED).
    2. Resolve current policy version.
    3. Lock snapshot.
    4. Insert HOLD_RELEASE (+minutes) and USAGE (-minutes).
    5. Update snapshot (held decreases, used increases).
    6. Update request status → APPROVED.
    7. Audit log with before/after.
    8. Commit.
    """
    time_off_request = await _get_request_or_404(session, auth.company_id, request_id)

    if time_off_request.status != RequestStatus.SUBMITTED.value:
        raise AppError("Only submitted requests can be approved", status_code=400)

    current_version = await _get_current_version(session, time_off_request.policy_id)
    if current_version is None:
        raise AppError("Policy has no active version", status_code=400)

    snapshot = await _get_or_create_snapshot_for_update(
        session, auth.company_id, time_off_request.employee_id, time_off_request.policy_id
    )

    before_dict = model_to_audit_dict(time_off_request)
    now = datetime.now(UTC)

    # HOLD_RELEASE: positive amount (credit, releases hold).
    hold_release = TimeOffLedgerEntry(
        company_id=auth.company_id,
        employee_id=time_off_request.employee_id,
        policy_id=time_off_request.policy_id,
        policy_version_id=current_version.id,
        entry_type=LedgerEntryType.HOLD_RELEASE.value,
        amount_minutes=time_off_request.requested_minutes,
        effective_at=now,
        source_type=LedgerSourceType.REQUEST.value,
        source_id=str(time_off_request.id),
    )
    session.add(hold_release)

    # USAGE: negative amount (debit).
    usage = TimeOffLedgerEntry(
        company_id=auth.company_id,
        employee_id=time_off_request.employee_id,
        policy_id=time_off_request.policy_id,
        policy_version_id=current_version.id,
        entry_type=LedgerEntryType.USAGE.value,
        amount_minutes=-time_off_request.requested_minutes,
        effective_at=now,
        source_type=LedgerSourceType.REQUEST.value,
        source_id=str(time_off_request.id),
    )
    session.add(usage)

    # Update snapshot: held decreases, used increases, available unchanged.
    snapshot.held_minutes -= time_off_request.requested_minutes
    snapshot.used_minutes += time_off_request.requested_minutes
    snapshot.available_minutes = snapshot.accrued_minutes - snapshot.used_minutes - snapshot.held_minutes
    snapshot.version += 1

    # Update request.
    time_off_request.status = RequestStatus.APPROVED.value
    time_off_request.decided_at = now
    time_off_request.decided_by = auth.user_id
    time_off_request.decision_note = payload.note if payload else None

    await session.flush()

    await write_audit_log(
        session,
        company_id=auth.company_id,
        actor_id=auth.user_id,
        entity_type=AuditEntityType.REQUEST,
        entity_id=time_off_request.id,
        action=AuditAction.APPROVE,
        before_json=before_dict,
        after_json=model_to_audit_dict(time_off_request),
    )

    await session.commit()
    await session.refresh(time_off_request)
    return _build_request_response(time_off_request)


async def deny_request(
    session: AsyncSession,
    auth: AuthContext,
    request_id: uuid.UUID,
    payload: DecisionPayload | None = None,
) -> RequestResponse:
    """Deny a submitted request: release the HOLD."""
    time_off_request = await _get_request_or_404(session, auth.company_id, request_id)

    if time_off_request.status != RequestStatus.SUBMITTED.value:
        raise AppError("Only submitted requests can be denied", status_code=400)

    return await _release_hold(
        session,
        time_off_request,
        auth,
        new_status=RequestStatus.DENIED,
        audit_action=AuditAction.DENY,
        decision_note=payload.note if payload else None,
    )


async def cancel_request(
    session: AsyncSession,
    auth: AuthContext,
    request_id: uuid.UUID,
) -> RequestResponse:
    """Cancel a submitted request: release the HOLD.

    The employee who submitted the request or an admin can cancel.
    """
    time_off_request = await _get_request_or_404(session, auth.company_id, request_id)

    if time_off_request.status != RequestStatus.SUBMITTED.value:
        raise AppError("Only submitted requests can be cancelled", status_code=400)

    # Authorization: employee can cancel own request, admin can cancel any.
    if auth.user_id != time_off_request.employee_id and auth.role != "admin":
        raise AppError("Not authorized to cancel this request", status_code=403)

    return await _release_hold(
        session,
        time_off_request,
        auth,
        new_status=RequestStatus.CANCELLED,
        audit_action=AuditAction.CANCEL,
    )


async def get_request(
    session: AsyncSession,
    company_id: uuid.UUID,
    request_id: uuid.UUID,
) -> RequestResponse:
    """Get a single request by ID."""
    time_off_request = await _get_request_or_404(session, company_id, request_id)
    return _build_request_response(time_off_request)


async def list_requests(
    session: AsyncSession,
    company_id: uuid.UUID,
    status_filter: str | None = None,
    policy_id: uuid.UUID | None = None,
    employee_id: uuid.UUID | None = None,
    offset: int = 0,
    limit: int = 50,
) -> RequestListResponse:
    """List requests with optional filters, ordered by created_at DESC."""
    base_filters = [col(TimeOffRequest.company_id) == company_id]

    if status_filter is not None:
        base_filters.append(col(TimeOffRequest.status) == status_filter)
    if policy_id is not None:
        base_filters.append(col(TimeOffRequest.policy_id) == policy_id)
    if employee_id is not None:
        base_filters.append(col(TimeOffRequest.employee_id) == employee_id)

    count_result = await session.execute(select(func.count()).select_from(TimeOffRequest).where(*base_filters))
    total = count_result.scalar_one()

    result = await session.execute(
        select(TimeOffRequest)
        .where(*base_filters)
        .order_by(col(TimeOffRequest.created_at).desc())
        .offset(offset)
        .limit(limit)
    )
    requests = list(result.scalars().all())

    return RequestListResponse(
        items=[_build_request_response(r) for r in requests],
        total=total,
    )
