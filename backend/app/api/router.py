from fastapi import APIRouter

from app.api.accruals import accrual_trigger_router, payroll_webhook_router
from app.api.assignments import company_assignments_router, employee_assignments_router, policy_assignments_router
from app.api.balances import adjustment_router, employee_balance_router, employee_ledger_router
from app.api.policies import router as policies_router
from app.api.requests import requests_router

api_router = APIRouter()
api_router.include_router(policies_router)
api_router.include_router(policy_assignments_router)
api_router.include_router(company_assignments_router)
api_router.include_router(employee_assignments_router)
api_router.include_router(employee_balance_router)
api_router.include_router(employee_ledger_router)
api_router.include_router(adjustment_router)
api_router.include_router(requests_router)
api_router.include_router(accrual_trigger_router)
api_router.include_router(payroll_webhook_router)
