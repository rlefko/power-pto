import logging
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import text

from app.config import get_settings
from app.db import SessionDep

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Health check response."""

    status: Literal["ok", "degraded", "error"]
    version: str
    environment: str


@router.get("/health", response_model=HealthResponse)
async def health(session: SessionDep) -> HealthResponse:
    """Return the health status of the API service."""
    settings = get_settings()
    status: Literal["ok", "degraded", "error"] = "ok"

    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Health check: database connectivity failed")
        status = "degraded"

    return HealthResponse(
        status=status,
        version=settings.app_version,
        environment=settings.environment,
    )
