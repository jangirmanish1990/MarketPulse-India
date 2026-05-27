"""Market router — index data, currency, and results calendar."""

from __future__ import annotations

import asyncio
import hashlib
import time as time_module
import uuid
from datetime import date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import CurrentUser
from backend.config import IST, get_market_status
from backend.database import get_db
from backend.market_hours import is_results_season
from backend.models import IndianStock
from backend.repositories import WatchlistRepo

router = APIRouter()

_SUMMARY_CACHE: dict[str, Any] = {}
_SUMMARY_EXPIRES: float = 0.0  # monotonic timestamp
_SUMMARY_TTL = 60.0  # seconds

DB = Annotated[AsyncSession, Depends(get_db)]

# ---------------------------------------------------------------------------
# Response models — market summary
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


# ---------------------------------------------------------------------------
# Response models — results calendar
# ---------------------------------------------------------------------------


class ResultsSeason(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    start: str  # ISO date YYYY-MM-DD
    end: str  # ISO date YYYY-MM-DD
    is_active: bool


class ResultsStockEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    nse_symbol: str
    company_name: str
    sector: str
    expected_time: str  # "pre-market" | "post-market"


class ResultsDay(BaseModel):
    model_config = ConfigDict(frozen=True)

    date: str  # ISO date YYYY-MM-DD
    stocks: list[ResultsStockEntry]


class ResultsCalendarResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    seasons: list[ResultsSeason]
    upcoming: list[ResultsDay]
    is_results_season: bool


# ---------------------------------------------------------------------------
# Results calendar — constants
# ---------------------------------------------------------------------------

_DEFAULT_WATCHLIST: list[str] = [
    "TCS",
    "INFY",
    "HDFCBANK",
    "RELIANCE",
    "WIPRO",
    "BAJFINANCE",
    "TITAN",
    "NESTLEIND",
    "SUNPHARMA",
    "AXISBANK",
]

# Built-in metadata for well-known NSE large-caps; used when a DB row is absent.
_STOCK_META: dict[str, tuple[str, str]] = {
    "TCS": ("Tata Consultancy Services Ltd", "IT"),
    "INFY": ("Infosys Ltd", "IT"),
    "WIPRO": ("Wipro Ltd", "IT"),
    "HCLTECH": ("HCL Technologies Ltd", "IT"),
    "HDFCBANK": ("HDFC Bank Ltd", "Banking"),
    "ICICIBANK": ("ICICI Bank Ltd", "Banking"),
    "AXISBANK": ("Axis Bank Ltd", "Banking"),
    "KOTAKBANK": ("Kotak Mahindra Bank Ltd", "Banking"),
    "SBIN": ("State Bank of India", "Banking"),
    "RELIANCE": ("Reliance Industries Ltd", "Energy"),
    "BAJFINANCE": ("Bajaj Finance Ltd", "Finance"),
    "TITAN": ("Titan Company Ltd", "Consumer"),
    "NESTLEIND": ("Nestle India Ltd", "FMCG"),
    "SUNPHARMA": ("Sun Pharmaceutical Industries Ltd", "Pharma"),
}

# IT-sector symbols get week-1/2 slots; banking gets week-2/3; all others week-2/4.
_IT_SYMBOLS: frozenset[str] = frozenset({"TCS", "INFY", "WIPRO", "HCLTECH"})
_BANK_SYMBOLS: frozenset[str] = frozenset(
    {"HDFCBANK", "ICICIBANK", "AXISBANK", "KOTAKBANK", "SBIN"}
)

# Three upcoming Indian quarterly results seasons.
_RESULT_SEASONS: list[tuple[str, date, date]] = [
    ("Q1 FY27 Results Season", date(2026, 7, 15), date(2026, 8, 15)),
    ("Q2 FY27 Results Season", date(2026, 10, 15), date(2026, 11, 15)),
    ("Q3 FY27 Results Season", date(2027, 1, 15), date(2027, 2, 15)),
]

# How many days ahead to look for upcoming results.
_UPCOMING_HORIZON_DAYS = 90


# ---------------------------------------------------------------------------
# Results calendar — pure helpers (no I/O)
# ---------------------------------------------------------------------------


def _sym_hash(sym: str) -> int:
    """Stable, process-seed-independent integer hash for *sym* (MD5-based).

    Python's built-in ``hash()`` is randomised per process run; MD5 gives the
    same integer for the same symbol on every request.
    """
    return int(hashlib.md5(sym.encode(), usedforsecurity=False).hexdigest(), 16)


def _season_offset_window(nse_symbol: str) -> tuple[int, int]:
    """Return (start_day_offset, end_day_offset) within a season for *nse_symbol*.

    Offsets are measured from the first day of the season.
    - IT stocks  → week 1–2 (days 0–13)
    - Banking    → week 2–3 (days 7–20)
    - Others     → week 2–4 (days 7–27)
    """
    if nse_symbol in _IT_SYMBOLS:
        return (0, 13)
    if nse_symbol in _BANK_SYMBOLS:
        return (7, 20)
    return (7, 27)


def _assign_result_date(nse_symbol: str, season_start: date) -> date:
    """Deterministically assign a weekday result date for *nse_symbol*.

    Picks from the eligible weekday window for the symbol's sector using a
    stable hash so the date is identical across requests.
    """
    start_off, end_off = _season_offset_window(nse_symbol)
    candidates: list[date] = [
        season_start + timedelta(days=delta)
        for delta in range(start_off, end_off + 1)
        if (season_start + timedelta(days=delta)).weekday() < 5  # Mon–Fri
    ]
    if not candidates:
        return season_start  # should never happen, but be safe
    return candidates[_sym_hash(nse_symbol) % len(candidates)]


def _expected_time(nse_symbol: str) -> str:
    """Return a realistic announcement-time label for *nse_symbol*."""
    if nse_symbol in _IT_SYMBOLS or nse_symbol in _BANK_SYMBOLS:
        return "post-market"
    # Other large-caps: most announce post-market; a minority pre-market.
    return "post-market" if _sym_hash(nse_symbol) % 4 != 0 else "pre-market"


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


@router.get("/market/results-calendar", response_model=ResultsCalendarResponse)
async def results_calendar(
    current_user: CurrentUser,
    db: DB,
) -> ResultsCalendarResponse:
    """Upcoming quarterly results dates for the user's watchlist stocks.

    Dates are assigned deterministically within the standard Indian results
    season windows so the response is stable across requests.

    Sector-based scheduling:
      - IT stocks (TCS, INFY, WIPRO, HCLTECH)  → week 1–2 of the season
      - Banking stocks                          → week 2–3
      - All others                              → week 2–4

    Falls back to a curated default watchlist when the user has no saved
    watchlist items.
    """
    today = datetime.now(IST).date()
    horizon = today + timedelta(days=_UPCOMING_HORIZON_DAYS)

    # ------------------------------------------------------------------
    # 1. Resolve the symbol list — user's watchlist, else defaults
    # ------------------------------------------------------------------
    symbols: list[str] = []
    try:
        user_id = uuid.UUID(current_user["user_id"])
        items = await WatchlistRepo(db).get_by_user(user_id)
        symbols = [item.nse_symbol for item in items]
    except Exception:
        # DB unavailable or query failure — proceed with defaults
        symbols = []

    if not symbols:
        symbols = list(_DEFAULT_WATCHLIST)

    # ------------------------------------------------------------------
    # 2. Enrich each symbol with (company_name, sector)
    #    Prefer the built-in dict; fall back to a DB lookup; then placeholders.
    # ------------------------------------------------------------------
    stock_info: dict[str, tuple[str, str]] = {}
    for sym in symbols:
        if sym in _STOCK_META:
            stock_info[sym] = _STOCK_META[sym]
        else:
            try:
                result = await db.execute(
                    select(IndianStock).where(IndianStock.nse_symbol == sym)
                )
                row = result.scalar_one_or_none()
                if row is not None:
                    stock_info[sym] = (row.company_name, row.sector or "Other")
                else:
                    stock_info[sym] = (sym, "Other")
            except Exception:
                stock_info[sym] = (sym, "Other")

    # ------------------------------------------------------------------
    # 3. Build the seasons list, marking the active season
    # ------------------------------------------------------------------
    seasons: list[ResultsSeason] = [
        ResultsSeason(
            name=name,
            start=s_start.isoformat(),
            end=s_end.isoformat(),
            is_active=(s_start <= today <= s_end),
        )
        for name, s_start, s_end in _RESULT_SEASONS
    ]

    # ------------------------------------------------------------------
    # 4. Assign result dates and group by date, filtered to horizon window
    # ------------------------------------------------------------------
    date_to_stocks: dict[date, list[ResultsStockEntry]] = {}

    for _name, s_start, s_end in _RESULT_SEASONS:
        # Skip seasons that don't overlap with [today, horizon]
        if s_end < today or s_start > horizon:
            continue

        for sym in symbols:
            assigned = _assign_result_date(sym, s_start)

            # Only include dates that fall inside [today, horizon]
            if assigned < today or assigned > horizon:
                continue

            company, sector = stock_info.get(sym, (sym, "Other"))
            entry = ResultsStockEntry(
                nse_symbol=sym,
                company_name=company,
                sector=sector,
                expected_time=_expected_time(sym),
            )
            date_to_stocks.setdefault(assigned, []).append(entry)

    # Sort results-days chronologically
    upcoming: list[ResultsDay] = [
        ResultsDay(date=d.isoformat(), stocks=stocks)
        for d, stocks in sorted(date_to_stocks.items())
    ]

    return ResultsCalendarResponse(
        seasons=seasons,
        upcoming=upcoming,
        is_results_season=is_results_season(),
    )
