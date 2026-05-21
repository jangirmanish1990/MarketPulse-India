"""Signals router — paginated signal history."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import CurrentUser
from backend.config import IST, SEBI_DISCLAIMER
from backend.database import get_db
from backend.models import Signal

router = APIRouter()

DB = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class SignalItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    signal_id: str
    nse_symbol: str
    direction: str
    confidence: float
    target_inr: float | None
    upside_pct: float | None
    horizon_days: int | None
    created_ist: str
    sebi_disclaimer: str


class SignalListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    signals: list[SignalItem]
    total: int
    sebi_disclaimer: str


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _to_item(sig: Signal) -> SignalItem:
    return SignalItem(
        signal_id=str(sig.id),
        nse_symbol=sig.nse_symbol,
        direction=sig.direction,
        confidence=sig.confidence,
        target_inr=sig.target_price_inr,
        upside_pct=sig.upside_pct,
        horizon_days=sig.time_horizon_days,
        created_ist=sig.created_at.astimezone(IST).isoformat(),
        sebi_disclaimer=SEBI_DISCLAIMER,
    )


# ---------------------------------------------------------------------------
# Endpoints — define literal route BEFORE parameterised route
# ---------------------------------------------------------------------------


@router.get("/signals/recent", response_model=SignalListResponse)
async def get_recent_signals(
    db: DB,
    current_user: CurrentUser,
) -> SignalListResponse:
    """Return the last 20 signals across all symbols, newest first."""
    stmt = select(Signal).order_by(Signal.created_at.desc()).limit(20)
    result = await db.execute(stmt)
    signals = list(result.scalars().all())
    return SignalListResponse(
        signals=[_to_item(s) for s in signals],
        total=len(signals),
        sebi_disclaimer=SEBI_DISCLAIMER,
    )


@router.get("/signals/{nse_symbol}", response_model=SignalListResponse)
async def get_signals_for_symbol(
    nse_symbol: str,
    db: DB,
    current_user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
    direction: Annotated[str | None, Query(pattern="^(BUY|HOLD|SELL)$")] = None,
) -> SignalListResponse:
    """Return paginated signal history for a single NSE symbol."""
    nse_symbol = nse_symbol.upper()

    stmt = select(Signal).where(Signal.nse_symbol == nse_symbol)
    if direction:
        stmt = stmt.where(Signal.direction == direction)
    stmt = stmt.order_by(Signal.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(stmt)
    signals = list(result.scalars().all())

    return SignalListResponse(
        signals=[_to_item(s) for s in signals],
        total=len(signals),
        sebi_disclaimer=SEBI_DISCLAIMER,
    )
