from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.main import app

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


async def test_health_returns_200(async_client: AsyncClient) -> None:
    response = await async_client.get("/health")
    assert response.status_code == 200


async def test_health_response_body(async_client: AsyncClient) -> None:
    response = await async_client.get("/health")
    data = response.json()
    assert data["status"] == "ok"
    assert data["version"] == "0.1.0"
    assert data["environment"] == "development"


async def test_health_response_schema(async_client: AsyncClient) -> None:
    response = await async_client.get("/health")
    data = response.json()
    assert set(data.keys()) == {"status", "version", "environment"}
    assert data["status"] in ("ok", "degraded", "error")


async def test_health_degraded_on_db_failure() -> None:
    """GET /health returns degraded status when the database is unreachable."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.execute.side_effect = ConnectionError("DB unreachable")

    async def _broken_session() -> AsyncIterator[AsyncSession]:
        yield mock_session

    app.dependency_overrides[get_session] = _broken_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/health")
        data = response.json()
        assert response.status_code == 200
        assert data["status"] == "degraded"
    finally:
        app.dependency_overrides.clear()
