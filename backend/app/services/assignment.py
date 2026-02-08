# ruff: noqa: TC003
from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlmodel import col

from app.exceptions import AppError
from app.models.assignment import TimeOffPolicyAssignment
from app.models.enums import AuditAction, AuditEntityType
from app.models.policy import TimeOffPolicy
from app.schemas.assignment import AssignmentListResponse, AssignmentResponse
from app.services.audit import model_to_audit_dict, write_audit_log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas.assignment import CreateAssignmentRequest
    from app.schemas.auth import AuthContext


def _build_assignment_response(assignment: TimeOffPolicyAssignment) -> AssignmentResponse:
    """Build an AssignmentResponse from a DB model."""
    return AssignmentResponse(
        id=assignment.id,
        company_id=assignment.company_id,
        employee_id=assignment.employee_id,
        policy_id=assignment.policy_id,
        effective_from=assignment.effective_from,
        effective_to=assignment.effective_to,
        created_by=assignment.created_by,
        created_at=assignment.created_at,
    )


async def _verify_policy_exists(
    session: AsyncSession,
    company_id: uuid.UUID,
    policy_id: uuid.UUID,
) -> TimeOffPolicy:
    """Verify a policy exists and belongs to the company. Raises 404 if not found."""
    result = await session.execute(
        select(TimeOffPolicy).where(
            col(TimeOffPolicy.id) == policy_id,
            col(TimeOffPolicy.company_id) == company_id,
        )
    )
    policy = result.scalar_one_or_none()
    if policy is None:
        raise AppError("Policy not found", status_code=404)
    return policy


async def _check_overlap(
    session: AsyncSession,
    company_id: uuid.UUID,
    employee_id: uuid.UUID,
    policy_id: uuid.UUID,
    effective_from: date,
    effective_to: date | None,
) -> None:
    """Check for overlapping assignments using half-open intervals [from, to)."""
    query = select(TimeOffPolicyAssignment).where(
        col(TimeOffPolicyAssignment.company_id) == company_id,
        col(TimeOffPolicyAssignment.employee_id) == employee_id,
        col(TimeOffPolicyAssignment.policy_id) == policy_id,
        or_(
            col(TimeOffPolicyAssignment.effective_to).is_(None),
            col(TimeOffPolicyAssignment.effective_to) > effective_from,
        ),
    )
    if effective_to is not None:
        query = query.where(col(TimeOffPolicyAssignment.effective_from) < effective_to)
    result = await session.execute(query)
    if result.scalar_one_or_none() is not None:
        raise AppError(
            "Assignment overlaps with an existing assignment for this employee and policy",
            status_code=409,
        )


async def create_assignment(
    session: AsyncSession,
    auth: AuthContext,
    policy_id: uuid.UUID,
    payload: CreateAssignmentRequest,
) -> AssignmentResponse:
    """Create a new policy assignment for an employee."""
    await _verify_policy_exists(session, auth.company_id, policy_id)
    await _check_overlap(
        session,
        auth.company_id,
        payload.employee_id,
        policy_id,
        payload.effective_from,
        payload.effective_to,
    )

    assignment = TimeOffPolicyAssignment(
        company_id=auth.company_id,
        employee_id=payload.employee_id,
        policy_id=policy_id,
        effective_from=payload.effective_from,
        effective_to=payload.effective_to,
        created_by=auth.user_id,
    )
    session.add(assignment)

    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raise AppError("Duplicate assignment", status_code=409) from None

    await write_audit_log(
        session,
        company_id=auth.company_id,
        actor_id=auth.user_id,
        entity_type=AuditEntityType.ASSIGNMENT,
        entity_id=assignment.id,
        action=AuditAction.CREATE,
        after_json=model_to_audit_dict(assignment),
    )

    await session.commit()
    await session.refresh(assignment)
    return _build_assignment_response(assignment)


async def list_assignments_by_policy(
    session: AsyncSession,
    company_id: uuid.UUID,
    policy_id: uuid.UUID,
    offset: int = 0,
    limit: int = 50,
) -> AssignmentListResponse:
    """List all assignments for a policy."""
    await _verify_policy_exists(session, company_id, policy_id)

    count_result = await session.execute(
        select(func.count())
        .select_from(TimeOffPolicyAssignment)
        .where(
            col(TimeOffPolicyAssignment.company_id) == company_id,
            col(TimeOffPolicyAssignment.policy_id) == policy_id,
        )
    )
    total = count_result.scalar_one()

    result = await session.execute(
        select(TimeOffPolicyAssignment)
        .where(
            col(TimeOffPolicyAssignment.company_id) == company_id,
            col(TimeOffPolicyAssignment.policy_id) == policy_id,
        )
        .order_by(col(TimeOffPolicyAssignment.effective_from).desc())
        .offset(offset)
        .limit(limit)
    )
    assignments = list(result.scalars().all())

    return AssignmentListResponse(
        items=[_build_assignment_response(a) for a in assignments],
        total=total,
    )


async def list_assignments_by_employee(
    session: AsyncSession,
    company_id: uuid.UUID,
    employee_id: uuid.UUID,
    offset: int = 0,
    limit: int = 50,
) -> AssignmentListResponse:
    """List all assignments for an employee."""
    count_result = await session.execute(
        select(func.count())
        .select_from(TimeOffPolicyAssignment)
        .where(
            col(TimeOffPolicyAssignment.company_id) == company_id,
            col(TimeOffPolicyAssignment.employee_id) == employee_id,
        )
    )
    total = count_result.scalar_one()

    result = await session.execute(
        select(TimeOffPolicyAssignment)
        .where(
            col(TimeOffPolicyAssignment.company_id) == company_id,
            col(TimeOffPolicyAssignment.employee_id) == employee_id,
        )
        .order_by(col(TimeOffPolicyAssignment.effective_from).desc())
        .offset(offset)
        .limit(limit)
    )
    assignments = list(result.scalars().all())

    return AssignmentListResponse(
        items=[_build_assignment_response(a) for a in assignments],
        total=total,
    )


async def end_date_assignment(
    session: AsyncSession,
    auth: AuthContext,
    assignment_id: uuid.UUID,
    effective_to: date,
) -> AssignmentResponse:
    """End-date an assignment (soft delete)."""
    result = await session.execute(
        select(TimeOffPolicyAssignment).where(
            col(TimeOffPolicyAssignment.id) == assignment_id,
            col(TimeOffPolicyAssignment.company_id) == auth.company_id,
        )
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise AppError("Assignment not found", status_code=404)

    if assignment.effective_to is not None:
        raise AppError("Assignment is already end-dated", status_code=400)

    if effective_to < assignment.effective_from:
        raise AppError("effective_to must be >= effective_from", status_code=400)

    before_dict = model_to_audit_dict(assignment)
    assignment.effective_to = effective_to
    await session.flush()

    await write_audit_log(
        session,
        company_id=auth.company_id,
        actor_id=auth.user_id,
        entity_type=AuditEntityType.ASSIGNMENT,
        entity_id=assignment.id,
        action=AuditAction.UPDATE,
        before_json=before_dict,
        after_json=model_to_audit_dict(assignment),
    )

    await session.commit()
    await session.refresh(assignment)
    return _build_assignment_response(assignment)


async def verify_active_assignment(
    session: AsyncSession,
    company_id: uuid.UUID,
    employee_id: uuid.UUID,
    policy_id: uuid.UUID,
    at_date: date,
) -> TimeOffPolicyAssignment:
    """Verify an employee has an active assignment to a policy on a given date.

    Uses half-open interval semantics: assignment is active when
    effective_from <= at_date AND (effective_to IS NULL OR effective_to > at_date).

    Raises AppError(400) if no active assignment is found.
    """
    result = await session.execute(
        select(TimeOffPolicyAssignment).where(
            col(TimeOffPolicyAssignment.company_id) == company_id,
            col(TimeOffPolicyAssignment.employee_id) == employee_id,
            col(TimeOffPolicyAssignment.policy_id) == policy_id,
            col(TimeOffPolicyAssignment.effective_from) <= at_date,
            or_(
                col(TimeOffPolicyAssignment.effective_to).is_(None),
                col(TimeOffPolicyAssignment.effective_to) > at_date,
            ),
        )
    )
    assignment = result.scalar_one_or_none()
    if assignment is None:
        raise AppError("Employee is not assigned to this policy on the given date", status_code=400)
    return assignment
