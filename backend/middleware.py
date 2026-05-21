"""Custom Starlette middleware for MarketPulse India.

Three middleware classes:
  ISTTimezoneMiddleware        — adds X-Timestamp-IST and X-Market-Status headers
  IndianStockValidatorMiddleware — returns 422 for unknown NSE symbols on key routes
  RequestLoggingMiddleware     — logs method / path / status / duration in IST
"""

from __future__ import annotations

import asyncio
import re
import time as time_module
from datetime import datetime

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from backend.config import IST, get_market_status

# ---------------------------------------------------------------------------
# Symbol-validation cache
# ---------------------------------------------------------------------------

_SYMBOL_PATH_RE = re.compile(r"^/api/(?:analyze|signals)/([A-Z][A-Z0-9&.-]{0,19})$")

_symbol_cache: set[str] = set()
_cache_expires_at: float = 0.0  # monotonic timestamp
_cache_lock: asyncio.Lock = asyncio.Lock()
_CACHE_TTL = 3600.0  # 1 hour


async def _load_symbol_cache() -> set[str]:
    """Return the set of valid NSE symbols, refreshing from DB at most once per hour."""
    global _symbol_cache, _cache_expires_at

    now = time_module.monotonic()
    if now < _cache_expires_at and _symbol_cache:
        return _symbol_cache

    async with _cache_lock:
        if time_module.monotonic() < _cache_expires_at and _symbol_cache:
            return _symbol_cache
        try:
            from sqlalchemy import text

            from backend.database import get_engine

            engine = get_engine()
            async with engine.connect() as conn:
                result = await conn.execute(text("SELECT nse_symbol FROM indian_stocks"))
                symbols: set[str] = {row[0] for row in result.fetchall()}
            if symbols:
                _symbol_cache = symbols
                _cache_expires_at = time_module.monotonic() + _CACHE_TTL
        except Exception:
            pass  # keep stale cache on DB error; route handler will fail anyway
    return _symbol_cache


# ---------------------------------------------------------------------------
# ISTTimezoneMiddleware
# ---------------------------------------------------------------------------


class ISTTimezoneMiddleware(BaseHTTPMiddleware):
    """Adds X-Timestamp-IST and X-Market-Status to every response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Timestamp-IST"] = datetime.now(IST).isoformat()
        response.headers["X-Market-Status"] = get_market_status()
        return response


# ---------------------------------------------------------------------------
# IndianStockValidatorMiddleware
# ---------------------------------------------------------------------------


class IndianStockValidatorMiddleware(BaseHTTPMiddleware):
    """Returns 422 for /analyze/{symbol} and /signals/{symbol} with unknown symbols.

    Skips validation when the symbol cache is empty (e.g., fresh install or DB
    unavailable) so that setup flows are not blocked.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        match = _SYMBOL_PATH_RE.match(request.url.path)
        if match:
            symbol = match.group(1)
            valid = await _load_symbol_cache()
            if valid and symbol not in valid:
                return JSONResponse(
                    status_code=422,
                    content={
                        "detail": (
                            f"Symbol {symbol} not found on NSE. "
                            "Try: INFY, TCS, RELIANCE, HDFCBANK"
                        )
                    },
                )
        return await call_next(request)


# ---------------------------------------------------------------------------
# RequestLoggingMiddleware
# ---------------------------------------------------------------------------


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs method, path, status, and duration in IST for every request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time_module.monotonic()
        response = await call_next(request)
        duration_ms = int((time_module.monotonic() - start) * 1000)
        now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
        print(
            f"[{now_ist}] {request.method} {request.url.path} "
            f"{response.status_code} {duration_ms}ms"
        )
        return response


__all__ = [
    "ISTTimezoneMiddleware",
    "IndianStockValidatorMiddleware",
    "RequestLoggingMiddleware",
]
