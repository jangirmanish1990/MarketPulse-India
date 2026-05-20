"""Node: web_search_fallback — augment context with live Indian news search."""

from __future__ import annotations

import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from agents.state import IndiaMarketState


def web_search_fallback(state: IndiaMarketState, config: RunnableConfig) -> dict[str, Any]:
    """Search the web for recent news when RAG returns too few relevant docs.

    TODO: replace stub with Tavily / Bing Search API call:
        query = f"{symbol} {announcement_type} India stock analysis"
        results = tavily.search(query, include_domains=["moneycontrol.com",
                                "economictimes.com", "nseindia.com"])
        new_docs = [{"source": r.url, "content": r.content} for r in results]
        # Append to retrieved_docs (don't replace — keep RAG results)
        return {"retrieved_docs": state["retrieved_docs"] + new_docs, ...}
    """
    start = time.monotonic()
    print(f"[web_search_fallback] Searching Indian news for {state['nse_symbol']}")

    return {
        "used_web_fallback": True,
        "node_timings": {
            **state["node_timings"],
            "web_search_fallback": round(time.monotonic() - start, 3),
        },
    }
