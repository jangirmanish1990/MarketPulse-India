"""Shared Redis cache helpers for all MCP servers.

Gracefully no-ops when Redis is unavailable — never raises.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import redis

logger = logging.getLogger(__name__)

_client: redis.Redis[str] | None = None
_unavailable: bool = False


def _get_client() -> redis.Redis[str] | None:
    global _client, _unavailable  # noqa: PLW0603
    if _unavailable:
        return None
    if _client is not None:
        return _client
    try:
        r: redis.Redis[str] = redis.Redis(
            host="localhost", port=6379, decode_responses=True
        )
        r.ping()
        _client = r
        return _client
    except Exception:
        _unavailable = True
        logger.debug("Redis unavailable — MCP caching disabled")
        return None


def cache_get(key: str) -> Any | None:
    """Return cached JSON value or None if key missing / Redis unavailable."""
    client = _get_client()
    if client is None:
        return None
    try:
        raw: str | None = client.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def cache_set(key: str, value: Any, ttl: int) -> None:
    """Store *value* JSON-encoded under *key* for *ttl* seconds; silently no-ops on failure."""
    client = _get_client()
    if client is None:
        return
    try:
        client.setex(key, ttl, json.dumps(value, default=str))
    except Exception:
        pass
