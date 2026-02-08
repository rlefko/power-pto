from fastapi import APIRouter

from app.api.assignments import company_assignments_router, employee_assignments_router, policy_assignments_router
from app.api.policies import router as policies_router

api_router = APIRouter()
api_router.include_router(policies_router)
api_router.include_router(policy_assignments_router)
api_router.include_router(company_assignments_router)
api_router.include_router(employee_assignments_router)
