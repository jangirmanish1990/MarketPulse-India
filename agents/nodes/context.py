"""Node: fetch_india_context — pull Nifty, FII, and macro data."""

from __future__ import annotations

import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from agents.state import IndiaMarketState


def fetch_india_context(state: IndiaMarketState, config: RunnableConfig) -> dict[str, Any]:
    """Fetch India-specific market context for the signal.

    TODO: replace stub with:
        - yfinance_india.get_index_data()  → nifty_value, nifty_change_pct
        - yfinance_india.get_usd_inr()     → usd_inr_context
        - nse.get_fii_dii_data()           → fii_net_flow_cr, fii_sentiment
        - Derive market_status from IST time
        - Lookup sector ETF for sector_index_change_pct
    """
    start = time.monotonic()
    print("[fetch_india_context] Fetching India context")

    return {
        "nifty_value": 23500.0,
        "nifty_change_pct": 0.0,
        "fii_sentiment": "neutral",
        "fii_net_flow_cr": 0.0,
        "usd_inr_context": "stable",
        "sector_index_change_pct": 0.0,
        "node_timings": {
            **state["node_timings"],
            "fetch_india_context": round(time.monotonic() - start, 3),
        },
    }
