"""Node: fetch_market_data — pull live quote, price history, and financials."""

from __future__ import annotations

import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from agents.state import IndiaMarketState


def fetch_market_data(state: IndiaMarketState, config: RunnableConfig) -> dict[str, Any]:
    """Fetch live market data for the symbol from yfinance-india-mcp and nse-mcp.

    TODO: replace stub with real MCP tool calls:
        - yfinance_india.get_price_history(symbol)
        - yfinance_india.get_financials(symbol)
        - nse.get_live_quote(symbol)
        - yfinance_india.get_index_data()
        - yfinance_india.get_usd_inr()
    """
    start = time.monotonic()
    print(f"[fetch_market_data] Fetching data for {state['nse_symbol']}")

    live_quote: dict[str, Any] = {"stub": True, "symbol": state["nse_symbol"]}

    return {
        "live_quote": live_quote,
        "node_timings": {
            **state["node_timings"],
            "fetch_market_data": round(time.monotonic() - start, 3),
        },
    }
