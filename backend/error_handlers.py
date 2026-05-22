"""FastAPI exception handlers for MarketPulse India.

Register all handlers in main.py after the app object is created.
Internal stack traces are never surfaced to callers — only structured JSON
with error_code, trace_id, and timestamp_ist.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.exceptions import MarketPulseError
from backend.logging_config import get_logger

IST = ZoneInfo("Asia/Kolkata")
log = get_logger(__name__)

# error_code → HTTP status
_STATUS_MAP: dict[str, int] = {
    "NSE_CONNECTION_FAILED": 503,
    "MCP_TIMEOUT": 504,
    "MCP_ERROR": 502,
    "RAG_RETRIEVAL_FAILED": 503,
    "EMBEDDING_FAILED": 503,
    "PARSE_FAILED": 422,
    "SIGNAL_FAILED": 503,
    "INVALID_TOKEN": 401,
    "UNAUTHORIZED": 403,
    "DATABASE_ERROR": 503,
    "STOCK_NOT_FOUND": 404,
    "WEBHOOK_AUTH_FAILED": 401,
}


def _make_error_response(
    request: Request,
    error_code: str,
    message: str,
    status_code: int,
    retriable: bool = False,
    details: dict[str, object] | None = None,
) -> JSONResponse:
    trace_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
    return JSONResponse(
        status_code=status_code,
        content={
            "error": True,
            "error_code": error_code,
            "message": message,
            "retriable": retriable,
            "details": details or {},
            "trace_id": trace_id,
            "timestamp_ist": datetime.now(IST).isoformat(),
        },
    )


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def marketpulse_error_handler(request: Request, exc: MarketPulseError) -> JSONResponse:
    status_code = _STATUS_MAP.get(exc.error_code, 500)
    log.warning(
        "domain_error",
        error_code=exc.error_code,
        message=exc.message,
        retriable=exc.retriable,
        path=str(request.url.path),
        status_code=status_code,
    )
    return _make_error_response(
        request=request,
        error_code=exc.error_code,
        message=exc.message,
        status_code=status_code,
        retriable=exc.retriable,
        details=exc.details,
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    log.info(
        "validation_error",
        path=str(request.url.path),
        errors=exc.errors(),
    )
    return _make_error_response(
        request=request,
        error_code="VALIDATION_ERROR",
        message="Request validation failed",
        status_code=422,
        details={"errors": exc.errors()},  # type: ignore[arg-type]
    )


_HTTP_CODE_MAP: dict[int, str] = {
    401: "INVALID_TOKEN",
    403: "UNAUTHORIZED",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
}


async def not_found_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    error_code = _HTTP_CODE_MAP.get(exc.status_code, f"HTTP_{exc.status_code}")
    message = (
        f"Resource not found: {request.url.path}"
        if exc.status_code == 404
        else str(exc.detail or error_code)
    )
    return _make_error_response(
        request=request,
        error_code=error_code,
        message=message,
        status_code=exc.status_code,
    )


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    log.error(
        "unhandled_exception",
        exc_type=type(exc).__name__,
        path=str(request.url.path),
        exc_info=exc,
    )
    return _make_error_response(
        request=request,
        error_code="INTERNAL_ERROR",
        message="An unexpected error occurred",
        status_code=500,
        retriable=True,
    )
