"""MarketPulse India — FastAPI entrypoint.

On startup the app verifies it can reach Postgres (3 retries, 5s apart).
`/health` reports both liveness and current DB connectivity.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

from backend.database import connect_with_retry, dispose_engine, ping_db

IST = ZoneInfo("Asia/Kolkata")

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Verify DB connectivity on boot; tear the engine down on shutdown."""
    try:
        await connect_with_retry()
    except Exception:
        logger.exception("Database unreachable after retries; aborting startup")
        raise
    try:
        yield
    finally:
        await dispose_engine()


app = FastAPI(
    title="MarketPulse India",
    description="Autonomous NSE/BSE stock intelligence agent.",
    version="0.1.0",
    lifespan=lifespan,
)


class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["ok", "degraded"]
    db: Literal["connected", "disconnected"]
    project: Literal["MarketPulse India"]
    version: str
    now_ist: datetime


@app.get("/health", response_model=HealthResponse, tags=["meta"])
async def health() -> HealthResponse:
    """Liveness + DB reachability probe. Returns IST timestamp."""
    db_ok = await ping_db()
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        db="connected" if db_ok else "disconnected",
        project="MarketPulse India",
        version=app.version,
        now_ist=datetime.now(IST),
    )
