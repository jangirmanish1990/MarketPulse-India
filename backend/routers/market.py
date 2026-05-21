"""Market router — index data, currency, and results calendar."""

from __future__ import annotations

import asyncio
import time as time_module
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from backend.auth import CurrentUser
from backend.config import IST, get_market_status

router = APIRouter()

_SUMMARY_CACHE: dict[str, Any] = {}
_SUMMARY_EXPIRES: float = 0.0  # monotonic timestamp
_SUMMARY_TTL = 60.0  # seconds


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class IndexData(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: float | None
    change_pct: float | None


class MarketSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    nifty50: IndexData
    sensex: IndexData
    nifty_bank: IndexData
    nifty_it: IndexData
    usd_inr: float | None
    market_status: str
    timestamp_ist: str


class ResultsWindow(BaseModel):
    model_config = ConfigDict(frozen=True)

    season: str
    start_date: str
    end_date: str
    description: str


class ResultsCalendar(BaseModel):
    model_config = ConfigDict(frozen=True)

    upcoming: list[ResultsWindow]
    note: str


# ---------------------------------------------------------------------------
# yfinance fetch (sync, run in thread)
# ---------------------------------------------------------------------------


def _fetch_yfinance() -> dict[str, Any]:
    """Fetch live index and currency data via yfinance (synchronous)."""
    import yfinance as yf

    def _get_value_and_change(ticker_sym: str) -> tuple[float | None, float | None]:
        try:
            hist = yf.Ticker(ticker_sym).history(period="2d")
            if hist.empty:
                return None, None
            close = float(hist["Close"].iloc[-1])
            prev = float(hist["Close"].iloc[-2]) if len(hist) > 1 else close
            chg = round((close - prev) / prev * 100, 2) if prev else None
            return round(close, 2), chg
        except Exception:
            return None, None

    nifty_val, nifty_chg = _get_value_and_change("^NSEI")
    sensex_val, sensex_chg = _get_value_and_change("^BSESN")
    bank_val, bank_chg = _get_value_and_change("^NSEBANK")
    it_val, it_chg = _get_value_and_change("^CNXIT")

    usdinr: float | None
    try:
        hist = yf.Ticker("USDINR=X").history(period="1d")
        usdinr = round(float(hist["Close"].iloc[-1]), 4) if not hist.empty else None
    except Exception:
        usdinr = None

    return {
        "nifty50": {"value": nifty_val, "change_pct": nifty_chg},
        "sensex": {"value": sensex_val, "change_pct": sensex_chg},
        "nifty_bank": {"value": bank_val, "change_pct": bank_chg},
        "nifty_it": {"value": it_val, "change_pct": it_chg},
        "usd_inr": usdinr,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/market/summary", response_model=MarketSummary)
async def market_summary(current_user: CurrentUser) -> MarketSummary:
    """Live index values and USD/INR rate; cached for 60 seconds."""
    global _SUMMARY_CACHE, _SUMMARY_EXPIRES

    now = time_module.monotonic()
    if now < _SUMMARY_EXPIRES and _SUMMARY_CACHE:
        data = _SUMMARY_CACHE
    else:
        try:
            data = await asyncio.to_thread(_fetch_yfinance)
            _SUMMARY_CACHE = data
            _SUMMARY_EXPIRES = time_module.monotonic() + _SUMMARY_TTL
        except Exception:
            data = _SUMMARY_CACHE or {
                "nifty50": {"value": None, "change_pct": None},
                "sensex": {"value": None, "change_pct": None},
                "nifty_bank": {"value": None, "change_pct": None},
                "nifty_it": {"value": None, "change_pct": None},
                "usd_inr": None,
            }

    def _idx(key: str) -> IndexData:
        raw = data.get(key, {})
        return IndexData(value=raw.get("value"), change_pct=raw.get("change_pct"))

    return MarketSummary(
        nifty50=_idx("nifty50"),
        sensex=_idx("sensex"),
        nifty_bank=_idx("nifty_bank"),
        nifty_it=_idx("nifty_it"),
        usd_inr=data.get("usd_inr"),
        market_status=get_market_status(),
        timestamp_ist=datetime.now(IST).isoformat(),
    )


@router.get("/market/results-calendar", response_model=ResultsCalendar)
async def results_calendar(current_user: CurrentUser) -> ResultsCalendar:
    """Upcoming quarterly results season dates.

    TODO (Week 5): fetch live dates from NSE corporate calendar API.
    """
    return ResultsCalendar(
        upcoming=[
            ResultsWindow(
                season="Q1 FY2027",
                start_date="2026-07-15",
                end_date="2026-08-15",
                description="April–June 2026 quarterly results season",
            ),
            ResultsWindow(
                season="Q4 FY2026",
                start_date="2026-04-15",
                end_date="2026-05-31",
                description="January–March 2026 quarterly results season",
            ),
        ],
        note="Dates are approximate. Results are typically declared over a 4-6 week window.",
    )
