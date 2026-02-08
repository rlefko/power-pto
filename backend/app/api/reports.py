# ruff: noqa: B008, TC001, TC003
from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api.deps import AdminDep, AuthDep, validate_company_scope
from app.db import SessionDep
from app.schemas.report import AuditLogListResponse, BalanceSummaryResponse, LedgerExportResponse
from app.services import report as report_service

reports_router = APIRouter(
    prefix="/companies/{company_id}",
    tags=["reports"],
    dependencies=[Depends(validate_company_scope)],
)


@reports_router.get(
    "/audit-log",
    response_model=AuditLogListResponse,
)
async def query_audit_log(
    company_id: uuid.UUID,
    session: SessionDep,
    auth: AdminDep,
    entity_type: str | None = Query(default=None),
    action: str | None = Query(default=None),
    actor_id: uuid.UUID | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> AuditLogListResponse:
    """Query audit log entries with optional filters (admin only)."""
    return await report_service.query_audit_log(
        session,
        company_id,
        entity_type=entity_type,
        action=action,
        actor_id=actor_id,
        start_date=start_date,
        end_date=end_date,
        offset=offset,
        limit=limit,
    )


@reports_router.get(
    "/reports/balances",
    response_model=BalanceSummaryResponse,
)
async def get_balance_summary(
    company_id: uuid.UUID,
    session: SessionDep,
    auth: AuthDep,
) -> BalanceSummaryResponse:
    """Get balance summary across all employees for a company."""
    return await report_service.get_company_balance_summary(session, company_id)


@reports_router.get(
    "/reports/ledger",
    response_model=LedgerExportResponse,
)
async def export_ledger(
    company_id: uuid.UUID,
    session: SessionDep,
    auth: AdminDep,
    policy_id: uuid.UUID | None = Query(default=None),
    employee_id: uuid.UUID | None = Query(default=None),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> LedgerExportResponse:
    """Export ledger entries with optional filters (admin only)."""
    return await report_service.export_ledger(
        session,
        company_id,
        policy_id=policy_id,
        employee_id=employee_id,
        start_date=start_date,
        end_date=end_date,
        offset=offset,
        limit=limit,
    )
