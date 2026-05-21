"""Stocks router — list and detail views for instruments in the DB."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import CurrentUser
from backend.config import IST, SEBI_DISCLAIMER
from backend.database import get_db
from backend.models import IndianStock, Signal
from backend.repositories import SignalRepo

router = APIRouter()

DB = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class StockBrief(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    company_name: str
    sector: str | None
    bse_code: str | None
    is_nifty50: bool
    is_sensex30: bool
    market_cap_cr: float | None


class SignalBrief(BaseModel):
    model_config = ConfigDict(frozen=True)

    direction: str
    confidence: float
    target_inr: float | None
    upside_pct: float | None
    created_ist: str
    sebi_disclaimer: str


class StockDetail(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    company_name: str
    sector: str | None
    bse_code: str | None
    is_nifty50: bool
    is_sensex30: bool
    market_cap_cr: float | None
    latest_signal: SignalBrief | None


class StockListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    stocks: list[StockBrief]
    total: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/stocks", response_model=StockListResponse)
async def list_stocks(
    db: DB,
    current_user: CurrentUser,
    sector: Annotated[str | None, Query()] = None,
    nifty50_only: Annotated[bool, Query()] = False,
) -> StockListResponse:
    """Return all instruments in the database, with optional filters."""
    stmt = select(IndianStock).order_by(IndianStock.nse_symbol)
    if nifty50_only:
        stmt = stmt.where(IndianStock.is_nifty50.is_(True))
    if sector:
        stmt = stmt.where(IndianStock.sector == sector)

    result = await db.execute(stmt)
    stocks = list(result.scalars().all())

    return StockListResponse(
        stocks=[
            StockBrief(
                symbol=s.nse_symbol,
                company_name=s.company_name,
                sector=s.sector,
                bse_code=s.bse_code,
                is_nifty50=s.is_nifty50,
                is_sensex30=s.is_sensex30,
                market_cap_cr=s.market_cap_cr,
            )
            for s in stocks
        ],
        total=len(stocks),
    )


@router.get("/stocks/{nse_symbol}", response_model=StockDetail)
async def get_stock(
    nse_symbol: str,
    db: DB,
    current_user: CurrentUser,
) -> StockDetail:
    """Return details for a single stock plus its latest signal if available."""
    nse_symbol = nse_symbol.upper()

    result = await db.execute(select(IndianStock).where(IndianStock.nse_symbol == nse_symbol))
    stock = result.scalar_one_or_none()
    if stock is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol {nse_symbol} not found.",
        )

    signals: list[Signal] = list(await SignalRepo(db).get_by_symbol(nse_symbol, limit=1))
    latest: SignalBrief | None = None
    if signals:
        sig = signals[0]
        latest = SignalBrief(
            direction=sig.direction,
            confidence=sig.confidence,
            target_inr=sig.target_price_inr,
            upside_pct=sig.upside_pct,
            created_ist=sig.created_at.astimezone(IST).isoformat(),
            sebi_disclaimer=SEBI_DISCLAIMER,
        )

    return StockDetail(
        symbol=stock.nse_symbol,
        company_name=stock.company_name,
        sector=stock.sector,
        bse_code=stock.bse_code,
        is_nifty50=stock.is_nifty50,
        is_sensex30=stock.is_sensex30,
        market_cap_cr=stock.market_cap_cr,
        latest_signal=latest,
    )
