"""Node: fetch_india_context — sector index, FII sentiment, market status, USD/INR."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from datetime import time as dt_time
from typing import Any
from zoneinfo import ZoneInfo

from langchain_core.runnables import RunnableConfig

from agents.state import IndiaMarketState
from backend.database import get_session_factory
from backend.repositories import IndianStockRepo

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

SECTOR_TO_INDEX: dict[str, str] = {
    "IT": "nifty_it",
    "Banking": "nifty_bank",
    "Financial Services": "nifty_bank",
    "FMCG": "nifty50",
    "Pharma": "nifty50",
    "Energy": "nifty50",
    "Metals": "nifty50",
}


def _market_status(now: datetime) -> str:
    """Derive NSE market session from current IST time and weekday."""
    t = now.time()
    wd = now.weekday()  # Mon=0 … Sun=6
    if wd >= 5:
        return "WEEKEND"
    if t < dt_time(9, 15):
        return "PRE_MARKET"
    if t < dt_time(15, 30):
        return "OPEN"
    if t < dt_time(16, 0):
        return "POST_MARKET"
    return "CLOSED"


async def fetch_india_context(state: IndiaMarketState, config: RunnableConfig) -> dict[str, Any]:
    """Derive India-specific context from fetched data and real-time clock.

    Reads:
      state["index_data"]   — populated by fetch_market_data
      state["usd_inr"]      — populated by fetch_market_data
      state["nifty_change_pct"] — populated by fetch_market_data

    Writes:
      sector_index_change_pct, fii_net_flow_cr, fii_sentiment,
      usd_inr_context, market_status
    """
    start = time.monotonic()
    symbol = state["nse_symbol"]

    # ── Sector lookup from indian_stocks table ────────────────────────────
    sector = ""
    try:
        factory = get_session_factory()
        async with factory() as db:
            repo = IndianStockRepo(db)
            stock = await repo.get_by_nse_symbol(symbol)
            sector = (stock.sector or "") if stock else ""
    except Exception as exc:
        logger.warning("[fetch_india_context] DB sector lookup failed: %s", exc)

    # ── Map sector → relevant index key ──────────────────────────────────
    sector_index_key = SECTOR_TO_INDEX.get(sector, "nifty50")
    index_data: dict[str, Any] = state["index_data"] or {}
    sector_idx: dict[str, Any] = index_data.get(sector_index_key) or {}
    sector_change_pct = float(sector_idx.get("change_pct") or 0)

    # ── FII flows — placeholder until Week 5 (real NSE BHAV data) ────────
    # TODO: replace with real intraday FII/DII data from NSE
    fii_net_flow_cr = 0.0
    fii_sentiment: str = "neutral"

    # ── USD/INR context — sector-aware ────────────────────────────────────
    usd_inr = state["usd_inr"]
    if sector == "IT":
        usd_inr_context = (
            "Weak INR — positive for IT export revenue"
            if usd_inr > 84
            else "Strong INR — mild headwind for IT exports"
        )
    else:
        usd_inr_context = f"USD/INR at {usd_inr:.2f}"

    # ── Market status from IST clock ─────────────────────────────────────
    now = datetime.now(IST)
    market_status = _market_status(now)

    nifty_change_pct = float(state["nifty_change_pct"])
    print(
        f"[fetch_india_context] {symbol} — "
        f"Nifty {nifty_change_pct:+.2f}% | FII: {fii_sentiment} | "
        f"Market: {market_status} | USD/INR: {usd_inr:.2f}"
    )

    return {
        "sector_index_change_pct": sector_change_pct,
        "fii_net_flow_cr": fii_net_flow_cr,
        "fii_sentiment": fii_sentiment,
        "usd_inr_context": usd_inr_context,
        "market_status": market_status,
        "node_timings": {
            **state["node_timings"],
            "fetch_india_context": round(time.monotonic() - start, 3),
        },
    }
