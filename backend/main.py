"""MarketPulse India — FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from backend.auth import router as auth_router
from backend.config import IST, get_market_status, limiter, settings
from backend.database import connect_with_retry, dispose_engine, ping_db
from backend.middleware import (
    ISTTimezoneMiddleware,
    IndianStockValidatorMiddleware,
    RequestLoggingMiddleware,
)
from backend.routers.analyze import router as analyze_router
from backend.routers.market import router as market_router
from backend.routers.signals import router as signals_router
from backend.routers.stocks import router as stocks_router
from backend.routers.watchlist import router as watchlist_router
from backend.routers.webhook import router as webhook_router


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Verify DB connectivity on boot; dispose engine on shutdown."""
    print("Starting MarketPulse India API...")
    await connect_with_retry()
    print("Database connected")
    yield
    await dispose_engine()
    print("Database disconnected")


app = FastAPI(
    title=settings.app_name,
    description="Autonomous NSE/BSE stock intelligence agent",
    version=settings.version,
    lifespan=lifespan,
)

# ── Rate limiting ──────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

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
app.include_router(signals_router, prefix="/api", tags=["Signals"])
app.include_router(watchlist_router, prefix="/api", tags=["Watchlist"])
app.include_router(market_router, prefix="/api", tags=["Market"])
app.include_router(stocks_router, prefix="/api", tags=["Stocks"])
app.include_router(webhook_router, prefix="/api", tags=["Webhook"])
app.include_router(auth_router, prefix="/api", tags=["Auth"])


# ── Health probe ──────────────────────────────────────────────────────────────


@app.get("/health", tags=["meta"])
async def health() -> dict[str, object]:
    """Liveness + DB reachability probe. Publicly accessible (no auth required)."""
    db_ok = await ping_db()
    return {
        "status": "ok" if db_ok else "degraded",
        "db": "connected" if db_ok else "disconnected",
        "service": "marketpulse-india",
        "version": settings.version,
        "now_ist": datetime.now(IST).isoformat(),
        "market_status": get_market_status(),
    }
