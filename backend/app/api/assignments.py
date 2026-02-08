# ruff: noqa: B008, TC001, TC003
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import AdminDep, AuthDep, validate_company_scope
from app.db import SessionDep
from app.schemas.assignment import AssignmentListResponse, AssignmentResponse, CreateAssignmentRequest
from app.services import assignment as assignment_service

policy_assignments_router = APIRouter(
    prefix="/companies/{company_id}/policies/{policy_id}/assignments",
    tags=["assignments"],
    dependencies=[Depends(validate_company_scope)],
)

company_assignments_router = APIRouter(
    prefix="/companies/{company_id}/assignments",
    tags=["assignments"],
    dependencies=[Depends(validate_company_scope)],
)

employee_assignments_router = APIRouter(
    prefix="/companies/{company_id}/employees/{employee_id}/assignments",
    tags=["assignments"],
    dependencies=[Depends(validate_company_scope)],
)


@policy_assignments_router.post("", response_model=AssignmentResponse, status_code=status.HTTP_201_CREATED)
async def create_assignment(
    policy_id: uuid.UUID,
    payload: CreateAssignmentRequest,
    session: SessionDep,
    auth: AdminDep,
) -> AssignmentResponse:
    """Assign an employee to a policy."""
    return await assignment_service.create_assignment(session, auth, policy_id, payload)


@policy_assignments_router.get("", response_model=AssignmentListResponse)
async def list_assignments_by_policy(
    policy_id: uuid.UUID,
    session: SessionDep,
    auth: AuthDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> AssignmentListResponse:
    """List all assignments for a policy."""
    return await assignment_service.list_assignments_by_policy(session, auth.company_id, policy_id, offset, limit)


@company_assignments_router.delete("/{assignment_id}", response_model=AssignmentResponse)
async def end_date_assignment(
    assignment_id: uuid.UUID,
    session: SessionDep,
    auth: AdminDep,
    effective_to: date = Query(default_factory=date.today),
) -> AssignmentResponse:
    """End-date an assignment (soft delete)."""
    return await assignment_service.end_date_assignment(session, auth, assignment_id, effective_to)


@employee_assignments_router.get("", response_model=AssignmentListResponse)
async def list_assignments_by_employee(
    employee_id: uuid.UUID,
    session: SessionDep,
    auth: AuthDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> AssignmentListResponse:
    """List all assignments for an employee."""
    return await assignment_service.list_assignments_by_employee(session, auth.company_id, employee_id, offset, limit)
