"""Node: grade_documents — LLM-based relevance grading for CRAG."""

from __future__ import annotations

import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from agents.state import IndiaMarketState


def grade_documents(state: IndiaMarketState, config: RunnableConfig) -> dict[str, Any]:
    """Grade each retrieved document for relevance to the current announcement.

    TODO: replace stub with llm_fast grading loop:
        For each doc in retrieved_docs:
            prompt = f"Is this relevant to {symbol} {announcement_type}? Answer: relevant/not_relevant"
            grade = llm_fast.invoke(prompt)
            doc_grades.append({"doc_id": ..., "relevance": grade, "confidence": ...})

    If fewer than 2 relevant docs are found, the conditional edge in graph.py
    will route to web_search_fallback.
    """
    start = time.monotonic()
    n_docs = len(state["retrieved_docs"])
    print(f"[grade_documents] Grading {n_docs} docs")

    return {
        "doc_grades": [{"relevance": "relevant", "confidence": 0.9}],
        "node_timings": {
            **state["node_timings"],
            "grade_documents": round(time.monotonic() - start, 3),
        },
    }
