"""Node: parse_announcement — extract structured fields from raw announcement text."""

from __future__ import annotations

import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from agents.state import IndiaMarketState


def parse_announcement(state: IndiaMarketState, config: RunnableConfig) -> dict[str, Any]:
    """Parse announcement_raw into a structured dict based on announcement_type.

    TODO: replace stub with llm_fast call using a type-specific extraction prompt:
        - quarterly_results  → revenue_cr, pat_cr, eps, yoy_growth_pct
        - board_meeting      → agenda, dividend_per_share, record_date
        - insider_trade      → trader_name, trade_type, quantity, price
        - shareholding       → promoter_pct, fii_pct, dii_pct, retail_pct
    """
    start = time.monotonic()
    print(f"[parse_announcement] Parsing {state['announcement_type']}")

    parsed_quarterly: dict[str, Any] | None = None
    parsed_board: dict[str, Any] | None = None
    parsed_insider: dict[str, Any] | None = None
    parsed_shp: dict[str, Any] | None = None

    if state["announcement_type"] == "quarterly_results":
        parsed_quarterly = {"stub": True}
    elif state["announcement_type"] == "board_meeting":
        parsed_board = {"stub": True}
    elif state["announcement_type"] == "insider_trade":
        parsed_insider = {"stub": True}
    elif state["announcement_type"] == "shareholding":
        parsed_shp = {"stub": True}

    return {
        "parsed_quarterly": parsed_quarterly,
        "parsed_board": parsed_board,
        "parsed_insider": parsed_insider,
        "parsed_shp": parsed_shp,
        "node_timings": {
            **state["node_timings"],
            "parse_announcement": round(time.monotonic() - start, 3),
        },
    }
