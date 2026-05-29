"""MarketPulse India — FastAPI application entry point."""

from __future__ import annotations

import asyncio
import os
import sys
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# psycopg v3 (used by LangGraph's AsyncPostgresSaver) requires SelectorEventLoop
# on Windows. Set this before uvicorn creates the event loop.
if sys.platform == "win32":
    import asyncio as _asyncio

    _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.auth import router as auth_router
from backend.config import IST, get_market_status, limiter, settings
from backend.database import connect_with_retry, dispose_engine, ping_db
from backend.error_handlers import (
    generic_error_handler,
    marketpulse_error_handler,
    not_found_handler,
    validation_error_handler,
)
from backend.exceptions import MarketPulseError
from backend.logging_config import get_logger, setup_logging
from backend.market_hours import process_queued_announcements
from backend.middleware import (
    IndianStockValidatorMiddleware,
    ISTTimezoneMiddleware,
    RequestLoggingMiddleware,
)
from backend.routers.analyze import router as analyze_router
from backend.routers.market import router as market_router
from backend.routers.sector import router as sector_router
from backend.routers.signals import router as signals_router
from backend.routers.stocks import router as stocks_router
from backend.routers.watchlist import router as watchlist_router
from backend.routers.webhook import router as webhook_router
from backend.routers.ws import router as ws_router

_scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")


_log = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Verify DB connectivity on boot; start scheduler; tear down on shutdown."""
    setup_logging()
    _log.info("starting", service="marketpulse-india")
    if not os.getenv("OPENAI_API_KEY"):
        _log.warning(
            "demo_mode_active",
            message=(
                "OPENAI_API_KEY is not set — running in DEMO mode. "
                "Health, signals history, and sector rankings are served from the DB. "
                "Live analysis pipeline returns an error until the key is configured."
            ),
        )
    await connect_with_retry()
    print("Database connected")

    # Process queued after-hours announcements at 9:15 AM IST every weekday
    _scheduler.add_job(
        process_queued_announcements,
        "cron",
        day_of_week="mon-fri",
        hour=9,
        minute=15,
        timezone="Asia/Kolkata",
    )
    _scheduler.start()
    _log.info("scheduler_started", job="process_queued_announcements", cron="09:15 IST mon-fri")

    yield

    _scheduler.shutdown(wait=False)
    await dispose_engine()
    _log.info("shutdown_complete")


app = FastAPI(
    title=settings.app_name,
    description="Autonomous NSE/BSE stock intelligence agent",
    version=settings.version,
    lifespan=lifespan,
)

# ── Rate limiting ──────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# ── Domain + generic exception handlers ───────────────────────────────────────
# Order matters: more specific handlers are checked first by Starlette.
app.add_exception_handler(MarketPulseError, marketpulse_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
app.add_exception_handler(StarletteHTTPException, not_found_handler)  # type: ignore[arg-type]
app.add_exception_handler(Exception, generic_error_handler)  # type: ignore[arg-type]

# ── CORS (allow all origins for development) ──────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Custom middleware
# add_middleware inserts at position 0, so the LAST add becomes outermost.
# Desired order (outermost → innermost):
#   ISTTimezoneMiddleware → RequestLoggingMiddleware → IndianStockValidatorMiddleware
app.add_middleware(IndianStockValidatorMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(ISTTimezoneMiddleware)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(analyze_router, prefix="/api", tags=["Analysis"])
app.include_router(sector_router, prefix="/api", tags=["Sector"])
app.include_router(signals_router, prefix="/api", tags=["Signals"])
app.include_router(watchlist_router, prefix="/api", tags=["Watchlist"])
app.include_router(market_router, prefix="/api", tags=["Market"])
app.include_router(stocks_router, prefix="/api", tags=["Stocks"])
app.include_router(webhook_router, prefix="/api", tags=["Webhook"])
app.include_router(auth_router, prefix="/api", tags=["Auth"])
# WebSocket endpoints — no /api prefix; paths are /ws/analyze/{session_id} and /ws/market
app.include_router(ws_router, tags=["WebSocket"])


# ── Health probe ──────────────────────────────────────────────────────────────


@app.get("/health", tags=["meta"])
async def health() -> dict[str, object]:
    """Liveness + DB reachability probe. Publicly accessible (no auth required)."""
    db_ok = await ping_db()
    return {
        "status": "ok" if db_ok else "degraded",
        "db": "connected" if db_ok else "disconnected",
        "demo_mode": not bool(os.getenv("OPENAI_API_KEY")),
        "service": "marketpulse-india",
        "version": settings.version,
        "now_ist": datetime.now(IST).isoformat(),
        "market_status": get_market_status(),
    }
