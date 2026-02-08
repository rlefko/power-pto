# ruff: noqa: B008, TC001, TC003
"""API endpoints for accrual triggers and payroll webhook."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api.deps import AdminDep, validate_company_scope
from app.db import SessionDep
from app.schemas.accrual import (
    AccrualRunResponse,
    PayrollProcessedPayload,
    PayrollProcessingResponse,
)
from app.services.accrual import process_payroll_event, run_time_based_accruals

# ---------------------------------------------------------------------------
# Admin trigger: POST /companies/{company_id}/accruals/trigger
# ---------------------------------------------------------------------------

accrual_trigger_router = APIRouter(
    prefix="/companies/{company_id}/accruals",
    tags=["accruals"],
    dependencies=[Depends(validate_company_scope)],
)


@accrual_trigger_router.post("/trigger", response_model=AccrualRunResponse)
async def trigger_accruals(
    session: SessionDep,
    auth: AdminDep,
    target_date: date | None = Query(default=None),
) -> AccrualRunResponse:
    """Manually trigger time-based accruals for a specific date (admin only).

    Useful for testing and backfills. Processes all active TIME accrual
    assignments for the authenticated company.
    """
    result = await run_time_based_accruals(
        session,
        target_date,
        company_id=auth.company_id,
    )
    return AccrualRunResponse(
        target_date=result.target_date,
        processed=result.processed,
        accrued=result.accrued,
        skipped=result.skipped,
        errors=result.errors,
    )


# ---------------------------------------------------------------------------
# Payroll webhook: POST /webhooks/payroll_processed
# ---------------------------------------------------------------------------

payroll_webhook_router = APIRouter(
    prefix="/webhooks",
    tags=["webhooks"],
)


@payroll_webhook_router.post("/payroll_processed", response_model=PayrollProcessingResponse)
async def payroll_processed(
    session: SessionDep,
    payload: PayrollProcessedPayload,
) -> PayrollProcessingResponse:
    """Receive payroll processed webhook and compute hours-worked accruals.

    Idempotent: replaying the same payroll_run_id produces no duplicates.
    The company_id comes from the payload body (not path/headers) since
    this endpoint is called by an external payroll service.
    """
    result = await process_payroll_event(session, payload)
    return PayrollProcessingResponse(
        payroll_run_id=result.payroll_run_id,
        processed=result.processed,
        accrued=result.accrued,
        skipped=result.skipped,
        errors=result.errors,
    )
