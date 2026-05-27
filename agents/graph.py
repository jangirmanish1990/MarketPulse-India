"""MarketPulse India — LangGraph StateGraph.

Graph topology (CRAG pattern):

    START
      └─► fetch_market_data
            └─► parse_announcement
                  └─► concall_analyzer
                        └─► fetch_india_context
                              └─► promoter_intelligence
                                    └─► retrieve_rag_context
                                          └─► grade_documents
                                                ├─[<2 relevant]─► web_search_fallback ─┐
                                                └─[≥2 relevant]──────────────────────► generate_analysis
                                                                                              └─► score_signal
                                                                                                     └─► END

LangSmith tracing is automatic when these env vars are set (see .env):
    LANGCHAIN_TRACING_V2=true
    LANGCHAIN_API_KEY=<key>
    LANGCHAIN_PROJECT=marketpulse-india
"""

from __future__ import annotations

from typing import Any

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, START, StateGraph

from agents.nodes import (
    concall_analyzer,
    fetch_india_context,
    fetch_market_data,
    generate_analysis,
    grade_documents,
    parse_announcement,
    promoter_intelligence,
    retrieve_rag_context,
    score_signal,
    web_search_fallback,
)
from agents.state import IndiaMarketState


# --------------------------------------------------------------------------- #
# Conditional edge — CRAG routing                                              #
# --------------------------------------------------------------------------- #


def should_web_search(state: IndiaMarketState) -> str:
    """Route to web_search_fallback when fewer than 2 relevant docs were graded.

    Returns a key that maps to a node name in add_conditional_edges.
    """
    doc_grades: list[Any] = state["doc_grades"]
    relevant = [
        d for d in doc_grades
        if isinstance(d, dict) and d.get("relevance") == "relevant"
    ]
    if len(relevant) < 2:
        return "web_search_fallback"
    return "generate_analysis"


# --------------------------------------------------------------------------- #
# Graph builder                                                                 #
# --------------------------------------------------------------------------- #


def build_graph() -> StateGraph:  # type: ignore[type-arg]
    """Return the uncompiled StateGraph.

    Call `.compile(checkpointer=...)` on the result to get a runnable graph.
    Typically done inside `async with get_checkpointer() as cp:` so the
    Postgres connection stays open for the lifetime of the graph.
    """
    graph: StateGraph = StateGraph(IndiaMarketState)  # type: ignore[type-arg]

    # ── Nodes ──────────────────────────────────────────────────────────────
    graph.add_node("fetch_market_data", fetch_market_data)  # type: ignore[arg-type]
    graph.add_node("parse_announcement", parse_announcement)  # type: ignore[arg-type]
    graph.add_node("concall_analyzer", concall_analyzer)  # type: ignore[arg-type]
    graph.add_node("fetch_india_context", fetch_india_context)  # type: ignore[arg-type]
    graph.add_node("promoter_intelligence", promoter_intelligence)  # type: ignore[arg-type]
    graph.add_node("retrieve_rag_context", retrieve_rag_context)  # type: ignore[arg-type]
    graph.add_node("grade_documents", grade_documents)  # type: ignore[arg-type]
    graph.add_node("web_search_fallback", web_search_fallback)  # type: ignore[arg-type]
    graph.add_node("generate_analysis", generate_analysis)  # type: ignore[arg-type]
    graph.add_node("score_signal", score_signal)  # type: ignore[arg-type]

    # ── Linear edges ───────────────────────────────────────────────────────
    graph.add_edge(START, "fetch_market_data")
    graph.add_edge("fetch_market_data", "parse_announcement")
    graph.add_edge("parse_announcement", "concall_analyzer")
    graph.add_edge("concall_analyzer", "fetch_india_context")
    graph.add_edge("fetch_india_context", "promoter_intelligence")
    graph.add_edge("promoter_intelligence", "retrieve_rag_context")
    graph.add_edge("retrieve_rag_context", "grade_documents")

    # ── CRAG conditional branch ────────────────────────────────────────────
    graph.add_conditional_edges(
        "grade_documents",
        should_web_search,  # type: ignore[arg-type]
        {
            "web_search_fallback": "web_search_fallback",
            "generate_analysis": "generate_analysis",
        },
    )

    graph.add_edge("web_search_fallback", "generate_analysis")
    graph.add_edge("generate_analysis", "score_signal")
    graph.add_edge("score_signal", END)

    return graph


def get_compiled_graph(checkpointer: AsyncPostgresSaver) -> Any:
    """Compile the graph with a Postgres checkpointer.

    The checkpointer must be obtained (and kept open) via:

        from agents.checkpointer import get_checkpointer
        async with get_checkpointer() as cp:
            graph = get_compiled_graph(cp)
            result = await graph.ainvoke(state, config=config)
    """
    return build_graph().compile(checkpointer=checkpointer)


__all__ = ["build_graph", "get_compiled_graph", "should_web_search"]
