"""Smoke test for the /health endpoint.

This is the only test on Day 1; it exists so the CI pipeline has at least
one assertion to run and the lint/types/test loop is exercised end-to-end.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app


@pytest.mark.asyncio
async def test_health_returns_ok() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "marketpulse-india"
    # `now_ist` is an ISO-8601 string with timezone info.
    parsed = datetime.fromisoformat(body["now_ist"])
    assert parsed.tzinfo is not None, "timestamp must be timezone-aware (IST)"
