"""Async SQLAlchemy engine + session factory for MarketPulse India.

Conventions:
    * `DATABASE_URL` is read from the environment. Never hardcode a URL.
    * The runtime driver is asyncpg (`postgresql+asyncpg://...`). On Neon,
      include `?ssl=require` in the URL.
    * `get_db` is the FastAPI dependency that yields an `AsyncSession`.
    * `connect_with_retry` is called from the app lifespan on startup; it
      retries 3 times at 5-second intervals before giving up.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from typing import Final

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration (env-driven only)
# ---------------------------------------------------------------------------
POOL_SIZE_MIN: Final[int] = 2
POOL_SIZE_MAX: Final[int] = 10
STARTUP_RETRY_ATTEMPTS: Final[int] = 3
STARTUP_RETRY_BACKOFF_SECONDS: Final[float] = 5.0


def _get_database_url() -> str:
    """Read `DATABASE_URL` from the environment. Raise if unset."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Set it in .env (see .env.example) or "
            "your deployment environment. The runtime driver must be asyncpg "
            "(URL prefix: 'postgresql+asyncpg://')."
        )
    return url


# ---------------------------------------------------------------------------
# Engine + session factory (built lazily so importing this module is cheap
# and tests can monkeypatch DATABASE_URL before the engine is constructed).
# ---------------------------------------------------------------------------
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, building it on first call."""
    global _engine
    if _engine is None:
        url = _get_database_url()
        _engine = create_async_engine(
            url,
            pool_size=POOL_SIZE_MIN,
            max_overflow=POOL_SIZE_MAX - POOL_SIZE_MIN,
            pool_pre_ping=True,
            pool_recycle=1800,  # recycle every 30 min — Neon idle-timeout safe
            future=True,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide session factory, building it on first call."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            class_=AsyncSession,
        )
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a fresh `AsyncSession` per request."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Startup connectivity check
# ---------------------------------------------------------------------------
async def connect_with_retry(
    attempts: int = STARTUP_RETRY_ATTEMPTS,
    backoff_seconds: float = STARTUP_RETRY_BACKOFF_SECONDS,
) -> None:
    """Verify the DB is reachable, retrying on transient failures.

    Raises the last exception after `attempts` failed tries.
    """
    engine = get_engine()
    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("Database reachable on attempt %d", attempt)
            return
        except Exception as exc:
            last_exc = exc
            logger.warning("DB connect attempt %d/%d failed: %s", attempt, attempts, exc)
            if attempt < attempts:
                await asyncio.sleep(backoff_seconds)
    assert last_exc is not None
    raise last_exc


async def ping_db() -> bool:
    """Quick health check used by the /health endpoint. Never raises."""
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        logger.exception("ping_db failed")
        return False
    return True


async def dispose_engine() -> None:
    """Tear down the engine on shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


__all__ = [
    "POOL_SIZE_MAX",
    "POOL_SIZE_MIN",
    "connect_with_retry",
    "dispose_engine",
    "get_db",
    "get_engine",
    "get_session_factory",
    "ping_db",
]
