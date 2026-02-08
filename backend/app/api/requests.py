# ruff: noqa: B008, TC001, TC003
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import AdminDep, AuthDep, validate_company_scope
from app.db import SessionDep
from app.schemas.request import (
    DecisionPayload,
    RequestListResponse,
    RequestResponse,
    SubmitRequestPayload,
)
from app.services import request as request_service

requests_router = APIRouter(
    prefix="/companies/{company_id}/requests",
    tags=["requests"],
    dependencies=[Depends(validate_company_scope)],
)


@requests_router.post("", response_model=RequestResponse, status_code=status.HTTP_201_CREATED)
async def submit_request(
    payload: SubmitRequestPayload,
    session: SessionDep,
    auth: AuthDep,
) -> RequestResponse:
    """Submit a new time-off request."""
    return await request_service.submit_request(session, auth, payload)


@requests_router.get("", response_model=RequestListResponse)
async def list_requests(
    session: SessionDep,
    auth: AuthDep,
    status_filter: str | None = Query(default=None, alias="status"),
    policy_id: uuid.UUID | None = Query(default=None),
    employee_id: uuid.UUID | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> RequestListResponse:
    """List time-off requests with optional filters."""
    return await request_service.list_requests(
        session, auth.company_id, status_filter, policy_id, employee_id, offset, limit
    )


@requests_router.get("/{request_id}", response_model=RequestResponse)
async def get_request(
    request_id: uuid.UUID,
    session: SessionDep,
    auth: AuthDep,
) -> RequestResponse:
    """Get a single time-off request."""
    return await request_service.get_request(session, auth.company_id, request_id)


@requests_router.post("/{request_id}/approve", response_model=RequestResponse)
async def approve_request(
    request_id: uuid.UUID,
    session: SessionDep,
    auth: AdminDep,
    payload: DecisionPayload | None = None,
) -> RequestResponse:
    """Approve a submitted time-off request (admin only)."""
    return await request_service.approve_request(session, auth, request_id, payload)


@requests_router.post("/{request_id}/deny", response_model=RequestResponse)
async def deny_request(
    request_id: uuid.UUID,
    session: SessionDep,
    auth: AdminDep,
    payload: DecisionPayload | None = None,
) -> RequestResponse:
    """Deny a submitted time-off request (admin only)."""
    return await request_service.deny_request(session, auth, request_id, payload)


@requests_router.post("/{request_id}/cancel", response_model=RequestResponse)
async def cancel_request(
    request_id: uuid.UUID,
    session: SessionDep,
    auth: AuthDep,
) -> RequestResponse:
    """Cancel a submitted time-off request."""
    return await request_service.cancel_request(session, auth, request_id)
