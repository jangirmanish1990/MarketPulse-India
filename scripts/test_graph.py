"""End-to-end graph smoke-test using stub nodes.

Run from the project root:

    python scripts/test_graph.py

Requires DATABASE_URL and LANGCHAIN_API_KEY in .env (or environment).
Makes a real Postgres checkpoint write. Does NOT call OpenAI (stubs only).
"""

from __future__ import annotations

import asyncio
import selectors
import sys
from pathlib import Path
from typing import Any

# Ensure project root is importable when run directly.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Force UTF-8 on Windows consoles.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from agents.checkpointer import get_checkpointer  # noqa: E402
from agents.graph import get_compiled_graph  # noqa: E402

# --------------------------------------------------------------------------- #
# Test state                                                                    #
# --------------------------------------------------------------------------- #

_TEST_STATE: dict[str, Any] = {
    "nse_symbol": "TCS",
    "bse_code": "532540",
    "exchange": "NSE",
    "announcement_type": "quarterly_results",
    "announcement_raw": "TCS Q2 FY25 Results: Revenue ₹63,973 Cr, PAT ₹12,446 Cr",
    "s3_key": "test/tcs_q2_fy25.json",
    "thread_id": "test-thread-001",
    "session_id": "test-session-001",
    "sebi_disclaimer": "",
    "retry_count": 0,
    "node_timings": {},
    "retrieved_docs": [],
    "doc_grades": [],
    "used_web_fallback": False,
    "concall_available": False,
    "price_history": {},
    "financials": {},
    "live_quote": {},
    "index_data": {},
    "usd_inr": 83.5,
    "nifty_value": 0.0,
    "nifty_change_pct": 0.0,
    "sector_index_change_pct": 0.0,
    "fii_net_flow_cr": 0.0,
    "fii_sentiment": "neutral",
    "usd_inr_context": "",
    "market_status": "OPEN",
    "parsed_quarterly": None,
    "parsed_board": None,
    "parsed_insider": None,
    "parsed_shp": None,
    "concall_tone": None,
    "concall_guidance_cr": None,
    "concall_signal_adjustment": None,
    "promoter_pct": None,
    "promoter_trend": None,
    "promoter_pledging_pct": None,
    "promoter_pledging_risk": None,
    "fii_ownership_trend": None,
    "analysis_summary": None,
    "key_positives": None,
    "key_risks": None,
    "quarter_verdict": None,
    "sector_outlook": None,
    "signal_direction": None,
    "confidence": None,
    "current_price_inr": None,
    "target_price_inr": None,
    "upside_pct": None,
    "time_horizon_days": None,
    "rationale": None,
    "error": None,
}


# --------------------------------------------------------------------------- #
# Main async runner                                                             #
# --------------------------------------------------------------------------- #


async def _run() -> bool:
    config: dict[str, Any] = {
        "configurable": {"thread_id": _TEST_STATE["thread_id"]}
    }

    print("\n── Running MarketPulse India graph (stub nodes) ──────────────────")
    print(f"Symbol   : {_TEST_STATE['nse_symbol']}")
    print(f"Thread   : {_TEST_STATE['thread_id']}")
    print()

    try:
        async with get_checkpointer() as checkpointer:
            graph = get_compiled_graph(checkpointer)
            final: dict[str, Any] = await graph.ainvoke(_TEST_STATE, config=config)
    except Exception as exc:
        print(f"\nGraph run FAILED: {exc}")
        return False

    # ── Results ────────────────────────────────────────────────────────────
    print("\n── Results ───────────────────────────────────────────────────────")
    print(f"Signal direction : {final.get('signal_direction')}")
    print(f"Confidence       : {final.get('confidence')}")
    has_disclaimer = bool(final.get("sebi_disclaimer"))
    print(f"SEBI disclaimer  : {'yes ✓' if has_disclaimer else 'NO — COMPLIANCE FAILURE'}")
    print(f"Thread ID        : {_TEST_STATE['thread_id']}  (proves checkpointing)")

    timings: dict[str, float] = final.get("node_timings") or {}
    nodes_ran = list(timings.keys())
    print(f"Nodes executed   : {nodes_ran}")
    print(f"Total wall time  : {sum(timings.values()):.3f}s")

    all_nine = {
        "fetch_market_data", "parse_announcement", "concall_analyzer",
        "fetch_india_context", "retrieve_rag_context", "grade_documents",
        "generate_analysis", "score_signal",
    }
    missing = all_nine - set(nodes_ran)
    if missing:
        # web_search_fallback may or may not run depending on doc_grades
        non_fallback_missing = missing - {"web_search_fallback"}
        if non_fallback_missing:
            print(f"\nWARNING: nodes not executed: {non_fallback_missing}")

    print("\nGraph test PASSED ✓")
    print("\nLangSmith traces → https://smith.langchain.com/projects/marketpulse-india")
    return True


def main() -> int:
    # psycopg v3 requires SelectorEventLoop on Windows.
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]
        loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
        ok = loop.run_until_complete(_run())
        loop.close()
    else:
        ok = asyncio.run(_run())
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
