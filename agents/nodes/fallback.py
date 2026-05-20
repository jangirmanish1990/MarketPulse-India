"""Node: web_search_fallback — Indian news RSS fallback when RAG is insufficient."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from agents.state import IndiaMarketState
from mcp_servers.indian_news.server import search_stock_news


async def web_search_fallback(state: IndiaMarketState, config: RunnableConfig) -> dict[str, Any]:
    """Augment retrieved_docs with live Indian news when RAG grades are poor.

    Searches ET Markets, Moneycontrol, LiveMint, and Business Standard RSS
    feeds for the symbol. Appends up to 5 articles as RAG-compatible docs
    without replacing existing vector store results.
    """
    start = time.monotonic()
    symbol: str = state["nse_symbol"]

    print(f"[web_search_fallback] RAG insufficient — searching Indian news for {symbol}")

    # Try to look up the full company name for a better headline match
    company_name = ""
    try:
        from backend.database import get_session_factory
        from backend.repositories import IndianStockRepo

        async with get_session_factory()() as session:
            stock = await IndianStockRepo(session).get_by_nse_symbol(symbol)
            if stock:
                company_name = stock.company_name
    except Exception:  # noqa: S110
        pass  # Company name is optional — search degrades to symbol only

    news: list[dict[str, Any]] = await asyncio.to_thread(search_stock_news, symbol, company_name, 7)

    fallback_docs: list[dict[str, Any]] = []
    for article in news[:5]:
        headline: str = article.get("headline", "")
        summary: str = article.get("summary", "")
        fallback_docs.append(
            {
                "content": f"{headline}\n{summary}".strip(),
                "metadata": {
                    "source": article.get("source", ""),
                    "nse_symbol": symbol,
                    "announcement_type": "news",
                    "sentiment": article.get("sentiment", "neutral"),
                    "url": article.get("url", ""),
                },
                "score": 0.5,
            }
        )

    existing: list[Any] = state.get("retrieved_docs") or []  # type: ignore[assignment]
    combined = existing + fallback_docs

    print(
        f"[web_search_fallback] Added {len(fallback_docs)} articles "
        f"from ET/Moneycontrol/Mint (total docs: {len(combined)})"
    )

    return {
        "retrieved_docs": combined,
        "used_web_fallback": True,
        "node_timings": {
            **state["node_timings"],
            "web_search_fallback": round(time.monotonic() - start, 3),
        },
    }
