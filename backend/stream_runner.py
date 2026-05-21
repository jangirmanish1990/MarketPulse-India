"""Streaming LangGraph runner — emits WebSocket events for every node execution."""

from __future__ import annotations

from typing import Any

from agents.checkpointer import get_checkpointer
from agents.graph import get_compiled_graph
from backend.websocket_manager import manager

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


async def run_graph_with_streaming(
    state: dict[str, Any],
    session_id: str,
    thread_id: str,
) -> dict[str, Any]:
    """Run the compiled LangGraph pipeline and emit WebSocket events per node.

    Broadcasts node_start / node_complete / tool_call events as each node runs,
    then emits a final signal_complete event with the resulting signal.
    Returns the accumulated final state.
    """
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}

    await manager.broadcast(
        session_id,
        {
            "type": "pipeline_start",
            "session_id": session_id,
            "symbol": state["nse_symbol"],
            "announcement_type": state["announcement_type"],
            "message": f"Starting analysis for {state['nse_symbol']}",
        },
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
                    meta = NODE_META[name]
                    await manager.broadcast(
                        session_id,
                        {
                            "type": "node_start",
                            "node": name,
                            "label": meta["label"],
                            "color": meta["color"],
                            "icon": meta["icon"],
                            "message": f"{meta['icon']} {meta['label']}...",
                        },
                    )

                elif event_type == "on_chain_end" and name in NODE_META:
                    meta = NODE_META[name]
                    output: Any = event.get("data", {}).get("output", {})
                    summary = _build_node_summary(name, output)

                    await manager.broadcast(
                        session_id,
                        {
                            "type": "node_complete",
                            "node": name,
                            "label": meta["label"],
                            "color": meta["color"],
                            "icon": meta["icon"],
                            "summary": summary,
                            "message": f"{meta['icon']} {meta['label']} done",
                        },
                    )

                    if isinstance(output, dict):
                        final_state.update(output)

                elif event_type == "on_tool_start":
                    await manager.broadcast(
                        session_id,
                        {
                            "type": "tool_call",
                            "tool": name,
                            "message": f"🔧 Calling {name}...",
                        },
                    )

    except Exception as exc:
        await manager.broadcast(
            session_id,
            {
                "type": "error",
                "error": str(exc),
                "message": f"Pipeline error: {exc}",
            },
        )
        raise

    signal_dir: str = str(final_state.get("signal_direction") or "HOLD")
    confidence: float = float(final_state.get("confidence") or 0.5)
    target: float = float(final_state.get("target_price_inr") or 0)
    upside: float = float(final_state.get("upside_pct") or 0)
    emoji = _DIRECTION_EMOJI.get(signal_dir, "⚪")

    await manager.broadcast(
        session_id,
        {
            "type": "signal_complete",
            "signal": {
                "direction": signal_dir,
                "confidence": confidence,
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
    )

    return final_state


__all__ = ["NODE_META", "run_graph_with_streaming"]
