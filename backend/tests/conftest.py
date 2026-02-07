from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import get_settings
from app.db import get_session
from app.main import app
from app.models import SQLModel

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    """Create a session-scoped async engine and ensure tables exist.

    In CI, Alembic migrations run before tests so create_all is a no-op.
    For local runs without prior migrations it serves as a fallback.
    """
    settings = get_settings()
    _engine = create_async_engine(settings.database_url)
    async with _engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield _engine
    async with _engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    await _engine.dispose()


@pytest.fixture
async def db_session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Yield a database session wrapped in a transaction that rolls back after each test."""
    async with engine.connect() as conn:
        txn = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)
        yield session
        await session.close()
        await txn.rollback()


@pytest.fixture
async def async_client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """Async HTTP client with the database session dependency overridden."""

    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
