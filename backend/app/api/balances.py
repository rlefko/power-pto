# ruff: noqa: B008, TC001, TC003
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import AdminDep, AuthDep, validate_company_scope
from app.db import SessionDep
from app.schemas.balance import (
    BalanceListResponse,
    CreateAdjustmentRequest,
    LedgerEntryResponse,
    LedgerListResponse,
)
from app.services import balance as balance_service

employee_balance_router = APIRouter(
    prefix="/companies/{company_id}/employees/{employee_id}/balances",
    tags=["balances"],
    dependencies=[Depends(validate_company_scope)],
)

employee_ledger_router = APIRouter(
    prefix="/companies/{company_id}/employees/{employee_id}/ledger",
    tags=["balances"],
    dependencies=[Depends(validate_company_scope)],
)

adjustment_router = APIRouter(
    prefix="/companies/{company_id}/adjustments",
    tags=["balances"],
    dependencies=[Depends(validate_company_scope)],
)


@employee_balance_router.get("", response_model=BalanceListResponse)
async def get_employee_balances(
    employee_id: uuid.UUID,
    session: SessionDep,
    auth: AuthDep,
) -> BalanceListResponse:
    """Get all policy balances for an employee."""
    return await balance_service.get_employee_balances(session, auth.company_id, employee_id)


@employee_ledger_router.get("", response_model=LedgerListResponse)
async def get_employee_ledger(
    employee_id: uuid.UUID,
    session: SessionDep,
    auth: AuthDep,
    policy_id: uuid.UUID = Query(),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> LedgerListResponse:
    """Get paginated ledger entries for an employee and policy."""
    return await balance_service.get_employee_ledger(session, auth.company_id, employee_id, policy_id, offset, limit)


@adjustment_router.post("", response_model=LedgerEntryResponse, status_code=status.HTTP_201_CREATED)
async def create_adjustment(
    payload: CreateAdjustmentRequest,
    session: SessionDep,
    auth: AdminDep,
) -> LedgerEntryResponse:
    """Create an admin balance adjustment."""
    return await balance_service.create_adjustment(session, auth, payload)
