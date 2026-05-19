"""MarketPulse India — FastAPI entrypoint.

Day 1: only a /health endpoint so we can verify the server starts. Routers
for market data, signals, etc. will be wired in here as they're built.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

IST = ZoneInfo("Asia/Kolkata")

app = FastAPI(
    title="MarketPulse India",
    description="Autonomous NSE/BSE stock intelligence agent.",
    version="0.1.0",
)


class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["ok"]
    service: Literal["marketpulse-india"]
    version: str
    now_ist: datetime


@app.get("/health", response_model=HealthResponse, tags=["meta"])
async def health() -> HealthResponse:
    """Liveness probe. Returns the current IST time so clock issues surface fast."""
    return HealthResponse(
        status="ok",
        service="marketpulse-india",
        version=app.version,
        now_ist=datetime.now(IST),
    )
