"""Smoke test for the /health endpoint.

Day 2: /health now also reports DB connectivity. To avoid requiring a live
Postgres in CI / on a clean dev machine, we patch the lifespan + the DB
ping so the route can be exercised in isolation.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient

import backend.database as db_module
import backend.main as main_module

if TYPE_CHECKING:
    from fastapi import FastAPI


@asynccontextmanager
async def _noop_lifespan(_app: FastAPI) -> AsyncIterator[None]:
    yield


@pytest.mark.asyncio
async def test_health_reports_db_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_ping() -> bool:
        return True

    monkeypatch.setattr(db_module, "ping_db", fake_ping)
    monkeypatch.setattr(main_module, "ping_db", fake_ping)

    main_module.app.router.lifespan_context = _noop_lifespan

    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db"] == "connected"
    assert body["project"] == "MarketPulse India"
    parsed = datetime.fromisoformat(body["now_ist"])
    assert parsed.tzinfo is not None


@pytest.mark.asyncio
async def test_health_reports_db_disconnected(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_ping() -> bool:
        return False

    monkeypatch.setattr(db_module, "ping_db", fake_ping)
    monkeypatch.setattr(main_module, "ping_db", fake_ping)

    main_module.app.router.lifespan_context = _noop_lifespan

    transport = ASGITransport(app=main_module.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["db"] == "disconnected"
