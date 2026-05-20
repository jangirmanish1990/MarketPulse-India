"""Node: retrieve_rag_context — pgvector similarity search for CRAG pipeline."""

from __future__ import annotations

import asyncio
import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from agents.state import IndiaMarketState
from db.vector_store import get_vector_store


async def retrieve_rag_context(state: IndiaMarketState, config: RunnableConfig) -> dict[str, Any]:
    """Search pgvector for historical announcements relevant to the current one.

    Combines company-specific docs (k=6, higher priority) with general peer
    docs (k=4) and deduplicates by content prefix. Falls back gracefully
    when the vector store is empty or unreachable.
    """
    start = time.monotonic()
    symbol: str = state["nse_symbol"]
    announcement_type: str = state["announcement_type"]

    # Build a rich query from parsed fields available at this point
    parsed: dict[str, Any] = (
        state.get("parsed_quarterly")
        or state.get("parsed_board")
        or state.get("parsed_insider")
        or {}
    )  # type: ignore[assignment]

    verdict: str = state.get("quarter_verdict") or ""  # type: ignore[assignment]
    query = f"{symbol} {announcement_type}"
    if parsed:
        query += f" revenue growth PAT margins {verdict}"

    print(f"[retrieve_rag_context] Searching for: '{query}'")

    try:
        vs = get_vector_store()

        # Company-specific docs — highest relevance
        company_docs: list[tuple[Any, float]] = await asyncio.to_thread(
            vs.similarity_search_with_score,
            query,
            6,
            {"nse_symbol": symbol},
        )

        # Peer/context docs — broader market context (no filter)
        peer_docs: list[tuple[Any, float]] = await asyncio.to_thread(
            vs.similarity_search_with_score,
            query,
            4,
        )

        # Combine and deduplicate by content prefix
        seen: set[str] = set()
        all_docs: list[dict[str, Any]] = []
        for doc, score in company_docs + peer_docs:
            key: str = doc.page_content[:100]
            if key not in seen:
                seen.add(key)
                all_docs.append(
                    {
                        "content": doc.page_content,
                        "metadata": doc.metadata,
                        "score": float(score),
                    }
                )

        print(
            f"[retrieve_rag_context] Found {len(all_docs)} docs "
            f"({len(company_docs)} company + {len(peer_docs)} peer)"
        )

    except Exception as exc:
        print(f"[retrieve_rag_context] Vector store error: {exc} — returning empty docs")
        all_docs = []

    return {
        "retrieved_docs": all_docs,
        "node_timings": {
            **state["node_timings"],
            "retrieve_rag_context": round(time.monotonic() - start, 3),
        },
    }
