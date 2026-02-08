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
    PolicyVersionListResponse,
    UpdatePolicyRequest,
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


@router.put("/{policy_id}", response_model=PolicyResponse)
async def update_policy(
    policy_id: uuid.UUID,
    payload: UpdatePolicyRequest,
    session: SessionDep,
    auth: AdminDep,
) -> PolicyResponse:
    """Update a policy by creating a new version."""
    return await policy_service.update_policy(session, auth, policy_id, payload)


@router.get("/{policy_id}/versions", response_model=PolicyVersionListResponse)
async def list_policy_versions(
    policy_id: uuid.UUID,
    session: SessionDep,
    auth: AuthDep,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> PolicyVersionListResponse:
    """List all versions of a policy."""
    return await policy_service.list_policy_versions(session, auth.company_id, policy_id, offset, limit)
