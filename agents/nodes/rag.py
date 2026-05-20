"""Node: retrieve_rag_context — vector-search historical announcements."""

from __future__ import annotations

import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from agents.state import IndiaMarketState


def retrieve_rag_context(state: IndiaMarketState, config: RunnableConfig) -> dict[str, Any]:
    """Retrieve relevant historical announcements from PgVector.

    TODO: replace stub with:
        1. Embed announcement_raw with agents.llm.embeddings
        2. Query pgvector `announcement_embeddings` table (cosine similarity)
        3. Return top-k docs as list[dict] with keys:
               symbol, date, announcement_type, summary, similarity_score
        4. Also query for same symbol's prior quarterly results
    """
    start = time.monotonic()
    print(f"[retrieve_rag_context] Retrieving docs for {state['nse_symbol']}")

    return {
        "retrieved_docs": [{"stub": True}],
        "node_timings": {
            **state["node_timings"],
            "retrieve_rag_context": round(time.monotonic() - start, 3),
        },
    }
