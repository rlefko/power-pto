from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from httpx import AsyncClient


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
