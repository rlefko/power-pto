# ruff: noqa: TC001, TC003
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query

from app.api.deps import AdminDep, AuthDep, validate_company_scope
from app.db import SessionDep
from app.schemas.holiday import CreateHolidayRequest, HolidayListResponse, HolidayResponse
from app.services import holiday as holiday_service

holidays_router = APIRouter(
    prefix="/companies/{company_id}/holidays",
    tags=["holidays"],
    dependencies=[Depends(validate_company_scope)],
)


@holidays_router.post(
    "",
    response_model=HolidayResponse,
    status_code=201,
)
async def create_holiday(
    company_id: uuid.UUID,
    payload: CreateHolidayRequest,
    session: SessionDep,
    auth: AdminDep,
) -> HolidayResponse:
    """Create a company holiday (admin only)."""
    return await holiday_service.create_holiday(session, auth, payload)


@holidays_router.get(
    "",
    response_model=HolidayListResponse,
)
async def list_holidays(
    company_id: uuid.UUID,
    session: SessionDep,
    auth: AuthDep,
    year: int | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> HolidayListResponse:
    """List company holidays with optional year filter."""
    return await holiday_service.list_holidays(session, company_id, year, offset, limit)


@holidays_router.delete(
    "/{holiday_id}",
    status_code=204,
)
async def delete_holiday(
    company_id: uuid.UUID,
    holiday_id: uuid.UUID,
    session: SessionDep,
    auth: AdminDep,
) -> None:
    """Delete a company holiday (admin only)."""
    await holiday_service.delete_holiday(session, auth, holiday_id)
