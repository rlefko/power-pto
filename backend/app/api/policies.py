# ruff: noqa: TC001, TC003
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import AdminDep, AuthDep, validate_company_scope
from app.db import SessionDep
from app.schemas.policy import (
    CreatePolicyRequest,
    PolicyListResponse,
    PolicyResponse,
)
from app.services import policy as policy_service

router = APIRouter(
    prefix="/companies/{company_id}/policies",
    tags=["policies"],
    dependencies=[Depends(validate_company_scope)],
)


@router.post("", response_model=PolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_policy(
    payload: CreatePolicyRequest,
    session: SessionDep,
    auth: AdminDep,
) -> PolicyResponse:
    """Create a new time-off policy with its initial version."""
    return await policy_service.create_policy(session, auth, payload)


@router.get("", response_model=PolicyListResponse)
async def list_policies(
    session: SessionDep,
    auth: AuthDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> PolicyListResponse:
    """List all policies for the company."""
    return await policy_service.list_policies(session, auth.company_id, offset, limit)


@router.get("/{policy_id}", response_model=PolicyResponse)
async def get_policy(
    policy_id: uuid.UUID,
    session: SessionDep,
    auth: AuthDep,
) -> PolicyResponse:
    """Get a single policy with its current version."""
    return await policy_service.get_policy(session, auth.company_id, policy_id)
