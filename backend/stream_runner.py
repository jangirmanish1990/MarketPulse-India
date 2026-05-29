"""Streaming LangGraph runner — emits WebSocket events for every node execution."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from agents.checkpointer import get_checkpointer
from agents.graph import get_compiled_graph
from backend.monitoring import record_agent_run, record_mcp_call, record_retrieval
from backend.websocket_manager import manager

logger = logging.getLogger(__name__)

# Human-readable metadata for each node
NODE_META: dict[str, dict[str, str]] = {
    "fetch_market_data": {
        "label": "Fetching NSE + yfinance Data",
        "color": "#38BDF8",
        "icon": "📡",
    },
    "parse_announcement": {
        "label": "Parsing Announcement",
        "color": "#A78BFA",
        "icon": "📄",
    },
    "concall_analyzer": {
        "label": "Analyzing Concall Transcript",
        "color": "#818CF8",
        "icon": "🎙️",
    },
    "fetch_india_context": {
        "label": "Fetching India Market Context",
        "color": "#FF9500",
        "icon": "🇮🇳",
    },
    "promoter_intelligence": {
        "label": "Promoter & FII Intelligence",
        "color": "#F472B6",
        "icon": "🏦",
    },
    "retrieve_rag_context": {
        "label": "Retrieving Historical Context",
        "color": "#FBBF24",
        "icon": "🔍",
    },
    "grade_documents": {
        "label": "Grading Documents",
        "color": "#FBBF24",
        "icon": "⚖️",
    },
    "web_search_fallback": {
        "label": "Searching Indian News",
        "color": "#FB923C",
        "icon": "🌐",
    },
    "generate_analysis": {
        "label": "Generating Analysis",
        "color": "#34D399",
        "icon": "🧠",
    },
    "score_signal": {
        "label": "Scoring Signal",
        "color": "#00E676",
        "icon": "📈",
    },
}

_DIRECTION_EMOJI: dict[str, str] = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}

# Maps LangGraph node names to (mcp_name, tool) for MCPCallDuration metrics
_MCP_NODES: dict[str, tuple[str, str]] = {
    "fetch_market_data": ("yfinance-nse", "fetch_market_data"),
    "retrieve_rag_context": ("pgvector", "retrieve"),
    "web_search_fallback": ("indian-news", "search"),
}


def _build_node_summary(node_name: str, output: Any) -> dict[str, object]:
    """Extract a compact, node-specific summary dict from a node's output."""
    if not isinstance(output, dict):
        return {}

    summaries: dict[str, dict[str, object]] = {
        "fetch_market_data": {
            "ltp": output.get("live_quote", {}).get("ltp", 0),
            "nifty": output.get("nifty_value", 0),
            "usd_inr": output.get("usd_inr", 0),
        },
        "parse_announcement": {
            "type": output.get("announcement_type"),
            "verdict": output.get("quarter_verdict"),
            "revenue_cr": (
                output.get("parsed_quarterly", {}).get("revenue_cr")
                if output.get("parsed_quarterly")
                else None
            ),
        },
        "concall_analyzer": {
            "available": output.get("concall_available", False),
            "tone": output.get("concall_tone"),
            "adjustment": output.get("concall_signal_adjustment"),
        },
        "promoter_intelligence": {
            "pledging": output.get("promoter_pledging_risk"),
            "fii": output.get("fii_sentiment"),
            "confidence_impact": output.get("confidence"),
        },
        "retrieve_rag_context": {
            "docs_retrieved": len(output.get("retrieved_docs", [])),
        },
        "grade_documents": {
            "total": len(output.get("doc_grades", [])),
            "relevant": len(
                [d for d in output.get("doc_grades", []) if d.get("relevance") == "relevant"]
            ),
            "fallback": output.get("used_web_fallback", False),
        },
        "generate_analysis": {
            "verdict": output.get("quarter_verdict"),
            "sector": output.get("sector_outlook"),
            "sentiment": output.get("sentiment_score"),
        },
        "score_signal": {
            "direction": output.get("signal_direction"),
            "confidence": output.get("confidence"),
            "target": output.get("target_price_inr"),
        },
    }

    return summaries.get(node_name, {})


def _emit(
    session_id: str,
    event: dict[str, object],
    main_loop: asyncio.AbstractEventLoop | None,
) -> None:
    """Broadcast an event to connected WebSocket clients.

    When main_loop is provided the pipeline is running in a worker thread, so
    we schedule the broadcast onto the main event loop (where the WebSocket
    transports live) via run_coroutine_threadsafe.  Without it we fall back to
    ensure_future on the current loop.
    """
    if main_loop is not None:
        manager.broadcast_from_thread(session_id, event, main_loop)
    else:
        asyncio.ensure_future(manager.broadcast(session_id, event))


async def run_graph_with_streaming(
    state: dict[str, Any],
    session_id: str,
    thread_id: str,
    main_loop: asyncio.AbstractEventLoop | None = None,
) -> dict[str, Any]:
    """Run the compiled LangGraph pipeline and emit WebSocket events per node.

    Broadcasts node_start / node_complete / tool_call events as each node runs,
    then emits a final signal_complete event with the resulting signal.
    Returns the accumulated final state.
    """
    # Warn early if running inside a ProactorEventLoop (Windows default) —
    # psycopg async requires SelectorEventLoop.
    try:
        loop = asyncio.get_event_loop()
        if loop.__class__.__name__ == "ProactorEventLoop":
            print(
                "[stream_runner] WARNING: ProactorEventLoop detected — "
                "psycopg async will fail. Use SelectorEventLoop."
            )
    except Exception:
        logger.debug("Could not inspect event loop type")

    # Wait up to 3 s for the WebSocket client to connect before broadcasting.
    # The frontend opens the WS ~500 ms after the POST returns; without this
    # the pipeline_start event fires into a session with no listeners.
    for _ in range(6):
        if manager.is_connected(session_id):
            break
        await asyncio.sleep(0.5)

    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    pipeline_start = time.monotonic()
    node_starts: dict[str, float] = {}

    _emit(
        session_id,
        {
            "type": "pipeline_start",
            "session_id": session_id,
            "symbol": state["nse_symbol"],
            "announcement_type": state["announcement_type"],
            "message": f"Starting analysis for {state['nse_symbol']}",
        },
        main_loop,
    )

    final_state = dict(state)

    try:
        async with get_checkpointer() as checkpointer:
            graph = get_compiled_graph(checkpointer)

            async for event in graph.astream_events(  # type: ignore[union-attr]
                state,
                config=config,
                version="v2",
            ):
                event_type: str = event.get("event", "")
                name: str = event.get("name", "")

                if event_type == "on_chain_start" and name in NODE_META:
                    node_starts[name] = time.monotonic()
                    meta = NODE_META[name]
                    _emit(
                        session_id,
                        {
                            "type": "node_start",
                            "node": name,
                            "label": meta["label"],
                            "color": meta["color"],
                            "icon": meta["icon"],
                            "message": f"{meta['icon']} {meta['label']}...",
                        },
                        main_loop,
                    )

                elif event_type == "on_chain_end" and name in NODE_META:
                    node_ms = int((time.monotonic() - node_starts.get(name, pipeline_start)) * 1000)
                    meta = NODE_META[name]
                    output: Any = event.get("data", {}).get("output", {})
                    summary = _build_node_summary(name, output)

                    # MCP call timing for nodes that represent external I/O
                    if name in _MCP_NODES:
                        mcp_name, tool = _MCP_NODES[name]
                        record_mcp_call(mcp_name, tool, node_ms, success=True)

                    # RAG retrieval precision after grading
                    if name == "grade_documents" and isinstance(output, dict):
                        grades: list[Any] = output.get("doc_grades") or []
                        relevant = sum(1 for d in grades if d.get("relevance") == "relevant")
                        record_retrieval(
                            symbol=state["nse_symbol"],
                            docs_retrieved=len(grades),
                            docs_relevant=relevant,
                            used_fallback=bool(output.get("used_web_fallback")),
                        )

                    _emit(
                        session_id,
                        {
                            "type": "node_complete",
                            "node": name,
                            "duration_ms": node_ms,
                            "label": meta["label"],
                            "color": meta["color"],
                            "icon": meta["icon"],
                            "summary": summary,
                            "message": f"{meta['icon']} {meta['label']} done",
                        },
                        main_loop,
                    )

                    if isinstance(output, dict):
                        final_state.update(output)

                elif event_type == "on_tool_start":
                    _emit(
                        session_id,
                        {
                            "type": "tool_call",
                            "tool": name,
                            "message": f"🔧 Calling {name}...",
                        },
                        main_loop,
                    )

    except Exception as exc:
        total_ms = int((time.monotonic() - pipeline_start) * 1000)
        record_agent_run(symbol=state["nse_symbol"], duration_ms=total_ms, success=False)
        _emit(
            session_id,
            {
                "type": "error",
                "error": str(exc),
                "message": f"Pipeline error: {exc}",
            },
            main_loop,
        )
        raise

    total_ms = int((time.monotonic() - pipeline_start) * 1000)
    signal_direction: str | None = final_state.get("signal_direction")  # type: ignore[assignment]
    record_agent_run(
        symbol=state["nse_symbol"],
        duration_ms=total_ms,
        success=signal_direction is not None,
        signal=signal_direction,
    )

    signal_dir: str = str(final_state.get("signal_direction") or "HOLD")
    confidence: float = float(final_state.get("confidence") or 0.5)
    current: float = float(final_state.get("current_price_inr") or 0)
    target: float = float(final_state.get("target_price_inr") or 0)
    upside: float = float(final_state.get("upside_pct") or 0)
    emoji = _DIRECTION_EMOJI.get(signal_dir, "⚪")

    _emit(
        session_id,
        {
            "type": "signal_complete",
            "signal": {
                "direction": signal_dir,
                "confidence": confidence,
                "current_price_inr": current,
                "target_price_inr": target,
                "upside_pct": upside,
                "time_horizon_days": final_state.get("time_horizon_days", 60),
                "rationale": final_state.get("rationale", ""),
                "sebi_disclaimer": final_state.get("sebi_disclaimer", ""),
            },
            "message": (
                f"{emoji} Signal: {signal_dir} | "
                f"₹{target:.0f} target | "
                f"{upside:+.1f}% | "
                f"{confidence:.0%} confidence"
            ),
        },
        main_loop,
    )

    return final_state


__all__ = ["NODE_META", "run_graph_with_streaming"]
