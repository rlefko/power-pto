from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.main import app
from app.models import SQLModel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@pytest.fixture(scope="session")
async def setup_database() -> AsyncIterator[None]:
    """Create all tables before tests and drop them after."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def async_client() -> AsyncIterator[AsyncClient]:
    """Async HTTP client for testing FastAPI endpoints."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
