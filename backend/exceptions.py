"""MarketPulse India — application exception hierarchy.

All domain errors inherit from MarketPulseError so FastAPI's exception handler
can map them to structured JSON responses with consistent error_code / trace_id
fields. Never let these propagate as raw Python exceptions to the client.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")


class MarketPulseError(Exception):
    def __init__(
        self,
        message: str,
        error_code: str,
        retriable: bool = False,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.retriable = retriable
        self.details: dict[str, object] = details or {}
        self.timestamp_ist = datetime.now(IST).isoformat()


# ---------------------------------------------------------------------------
# MCP / connectivity errors
# ---------------------------------------------------------------------------


class NSEConnectionError(MarketPulseError):
    def __init__(self, symbol: str, reason: str = "") -> None:
        super().__init__(
            message=f"NSE connection failed for {symbol}: {reason}",
            error_code="NSE_CONNECTION_FAILED",
            retriable=True,
            details={"symbol": symbol, "reason": reason},
        )


class MCPTimeoutError(MarketPulseError):
    def __init__(self, mcp_name: str, tool: str) -> None:
        super().__init__(
            message=f"MCP timeout: {mcp_name}.{tool}",
            error_code="MCP_TIMEOUT",
            retriable=True,
            details={"mcp": mcp_name, "tool": tool},
        )


class MCPError(MarketPulseError):
    def __init__(self, mcp_name: str, message: str) -> None:
        super().__init__(
            message=f"MCP error in {mcp_name}: {message}",
            error_code="MCP_ERROR",
            retriable=False,
            details={"mcp": mcp_name},
        )


# ---------------------------------------------------------------------------
# RAG errors
# ---------------------------------------------------------------------------


class RAGRetrievalError(MarketPulseError):
    def __init__(self, reason: str) -> None:
        super().__init__(
            message=f"RAG retrieval failed: {reason}",
            error_code="RAG_RETRIEVAL_FAILED",
            retriable=True,
            details={"reason": reason},
        )


class EmbeddingError(MarketPulseError):
    def __init__(self, reason: str) -> None:
        super().__init__(
            message=f"Embedding failed: {reason}",
            error_code="EMBEDDING_FAILED",
            retriable=True,
            details={"reason": reason},
        )


# ---------------------------------------------------------------------------
# Parser errors
# ---------------------------------------------------------------------------


class AnnouncementParseError(MarketPulseError):
    def __init__(self, symbol: str, announcement_type: str) -> None:
        super().__init__(
            message=f"Failed to parse {announcement_type} for {symbol}",
            error_code="PARSE_FAILED",
            retriable=False,
            details={"symbol": symbol, "type": announcement_type},
        )


# ---------------------------------------------------------------------------
# Signal errors
# ---------------------------------------------------------------------------


class SignalGenerationError(MarketPulseError):
    def __init__(self, symbol: str, reason: str) -> None:
        super().__init__(
            message=f"Signal generation failed for {symbol}: {reason}",
            error_code="SIGNAL_FAILED",
            retriable=True,
            details={"symbol": symbol, "reason": reason},
        )


# ---------------------------------------------------------------------------
# Auth errors
# ---------------------------------------------------------------------------


class InvalidTokenError(MarketPulseError):
    def __init__(self) -> None:
        super().__init__(
            message="Invalid or expired token",
            error_code="INVALID_TOKEN",
            retriable=False,
        )


class UnauthorizedError(MarketPulseError):
    def __init__(self, resource: str = "") -> None:
        super().__init__(
            message=f"Unauthorized access{': ' + resource if resource else ''}",
            error_code="UNAUTHORIZED",
            retriable=False,
            details={"resource": resource},
        )


# ---------------------------------------------------------------------------
# Database errors
# ---------------------------------------------------------------------------


class DatabaseError(MarketPulseError):
    def __init__(self, operation: str, reason: str) -> None:
        super().__init__(
            message=f"Database {operation} failed: {reason}",
            error_code="DATABASE_ERROR",
            retriable=True,
            details={"operation": operation},
        )


# ---------------------------------------------------------------------------
# Stock / domain errors
# ---------------------------------------------------------------------------


class StockNotFoundError(MarketPulseError):
    def __init__(self, symbol: str) -> None:
        super().__init__(
            message=f"Stock {symbol} not found on NSE/BSE",
            error_code="STOCK_NOT_FOUND",
            retriable=False,
            details={"symbol": symbol},
        )


# ---------------------------------------------------------------------------
# Webhook errors
# ---------------------------------------------------------------------------


class WebhookAuthError(MarketPulseError):
    def __init__(self) -> None:
        super().__init__(
            message="Invalid webhook secret",
            error_code="WEBHOOK_AUTH_FAILED",
            retriable=False,
        )
