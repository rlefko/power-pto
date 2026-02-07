from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.router import api_router
from app.config import get_settings
from app.exceptions import setup_exception_handlers
from app.middleware import setup_middleware

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan manager for startup and shutdown."""
    settings = get_settings()
    print(f"Starting {settings.app_name} v{settings.app_version} [{settings.environment}]")
    yield
    print(f"Shutting down {settings.app_name}")


def create_app() -> FastAPI:
    """Application factory."""
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
        docs_url="/docs" if settings.environment != "production" else None,
        redoc_url="/redoc" if settings.environment != "production" else None,
    )

    setup_middleware(application, settings)
    setup_exception_handlers(application)

    application.include_router(health_router)
    application.include_router(api_router)

    return application


app = create_app()
