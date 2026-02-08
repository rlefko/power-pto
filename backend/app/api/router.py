from fastapi import APIRouter

from app.api.policies import router as policies_router

api_router = APIRouter()
api_router.include_router(policies_router)
