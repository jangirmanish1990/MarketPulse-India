"""Node: concall_analyzer — locate and analyse earnings call transcripts."""

from __future__ import annotations

import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from agents.state import IndiaMarketState


def concall_analyzer(state: IndiaMarketState, config: RunnableConfig) -> dict[str, Any]:
    """Search for and analyse concall transcripts for the symbol.

    TODO: replace stub with:
        1. Search S3 / NSE for concall PDF linked to the announcement
        2. If found: extract text, run llm_strong with concall tone prompt
        3. Set concall_tone, concall_guidance_cr, concall_signal_adjustment
    """
    start = time.monotonic()
    print(f"[concall_analyzer] Checking concall for {state['nse_symbol']}")

    return {
        "concall_available": False,
        "concall_tone": None,
        "concall_guidance_cr": None,
        "concall_signal_adjustment": None,
        "node_timings": {
            **state["node_timings"],
            "concall_analyzer": round(time.monotonic() - start, 3),
        },
    }
