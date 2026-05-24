"""Watchlist router — per-user stock watchlist with latest signal."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import CurrentUser
from backend.config import IST, SEBI_DISCLAIMER
from backend.database import get_db
from backend.models import IndianStock, Signal, User, WatchlistItem
from backend.repositories import SignalRepo, WatchlistRepo

router = APIRouter()

DB = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class LatestSignalBrief(BaseModel):
    model_config = ConfigDict(frozen=True)

    direction: str
    confidence: float
    current_price_inr: float | None
    target_price_inr: float | None
    upside_pct: float | None
    created_ist: str


class WatchlistEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    nse_symbol: str
    company_name: str
    sector: str | None
    bse_code: str | None
    added_ist: str
    latest_signal: LatestSignalBrief | None


class WatchlistResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    items: list[WatchlistEntry]
    total: int


class WatchlistAddResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    added: bool


class WatchlistRemoveResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    removed: bool


# ---------------------------------------------------------------------------
# DB user helper — creates the user row on first watchlist access
# ---------------------------------------------------------------------------


async def _get_or_create_db_user(user_info: dict[str, str], db: AsyncSession) -> uuid.UUID:
    user_id = uuid.UUID(user_info["user_id"])
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(id=user_id, email=user_info["email"])
        db.add(user)
        await db.flush()
    return user_id


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/watchlist", response_model=WatchlistResponse)
async def get_watchlist(
    db: DB,
    current_user: CurrentUser,
) -> WatchlistResponse:
    """Return the authenticated user's watchlist with the latest signal per stock."""
    user_id = await _get_or_create_db_user(current_user, db)  # type: ignore[arg-type]
    await db.commit()

    items = await WatchlistRepo(db).get_by_user(user_id)
    signal_repo = SignalRepo(db)

    entries: list[WatchlistEntry] = []
    for item in items:
        result = await db.execute(
            select(IndianStock).where(IndianStock.nse_symbol == item.nse_symbol)
        )
        stock = result.scalar_one_or_none()
        company_name = stock.company_name if stock else item.nse_symbol
        sector = stock.sector if stock else None
        bse_code = stock.bse_code if stock else None

        signals = await signal_repo.get_by_symbol(item.nse_symbol, limit=1)
        latest: LatestSignalBrief | None = None
        if signals:
            sig = signals[0]
            latest = LatestSignalBrief(
                direction=sig.direction,
                confidence=sig.confidence,
                current_price_inr=sig.current_price_inr,
                target_price_inr=sig.target_price_inr,
                upside_pct=sig.upside_pct,
                created_ist=sig.created_at.astimezone(IST).isoformat(),
            )

        entries.append(
            WatchlistEntry(
                nse_symbol=item.nse_symbol,
                company_name=company_name,
                sector=sector,
                bse_code=bse_code,
                added_ist=item.added_at.astimezone(IST).isoformat(),
                latest_signal=latest,
            )
        )

    return WatchlistResponse(items=entries, total=len(entries))


@router.post("/watchlist/{nse_symbol}", response_model=WatchlistAddResponse)
async def add_to_watchlist(
    nse_symbol: str,
    db: DB,
    current_user: CurrentUser,
) -> WatchlistAddResponse:
    """Add a symbol to the authenticated user's watchlist."""
    nse_symbol = nse_symbol.upper()

    result = await db.execute(select(IndianStock).where(IndianStock.nse_symbol == nse_symbol))
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol {nse_symbol} not found on NSE.",
        )

    user_id = await _get_or_create_db_user(current_user, db)  # type: ignore[arg-type]

    # Idempotent — skip if already in watchlist
    existing = await db.execute(
        select(WatchlistItem).where(
            WatchlistItem.user_id == user_id,
            WatchlistItem.nse_symbol == nse_symbol,
        )
    )
    if existing.scalar_one_or_none() is None:
        await WatchlistRepo(db).add(user_id=user_id, nse_symbol=nse_symbol)

    await db.commit()
    return WatchlistAddResponse(symbol=nse_symbol, added=True)


@router.delete("/watchlist/{nse_symbol}", response_model=WatchlistRemoveResponse)
async def remove_from_watchlist(
    nse_symbol: str,
    db: DB,
    current_user: CurrentUser,
) -> WatchlistRemoveResponse:
    """Remove a symbol from the authenticated user's watchlist."""
    nse_symbol = nse_symbol.upper()
    user_id = await _get_or_create_db_user(current_user, db)  # type: ignore[arg-type]

    removed = await WatchlistRepo(db).remove(user_id=user_id, nse_symbol=nse_symbol)
    await db.commit()
    return WatchlistRemoveResponse(symbol=nse_symbol, removed=removed)
