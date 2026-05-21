"""Full pipeline smoke-test — Day 10.

Runs the complete 9-node LangGraph pipeline with real INFY Q2FY25 data,
creates an analysis_session row so the signals FK passes, then verifies
the signal was persisted to PostgreSQL.

Run from project root:  python scripts/test_full_pipeline.py
"""

from __future__ import annotations

import asyncio
import selectors
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from agents.graph import build_graph  # noqa: E402
from backend.database import get_session_factory  # noqa: E402
from backend.repositories import AnalysisSessionRepo, SignalRepo  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")
_SEP = "=" * 58
_SEP2 = "-" * 58
_THREAD_ID = "pipeline-test-001"

_ANNOUNCEMENT = (
    "Infosys Q2 FY25 Results: Revenue 40986 crore "
    "up 5.1 percent YoY and 3.3 percent QoQ. "
    "Net Profit 6506 crore up 4.7 percent YoY. "
    "EPS 15.78. Operating margin 21.1 percent. "
    "FY25 revenue guidance raised to 4.5 to 5 percent "
    "constant currency. Large deal TCV 2.4 billion USD. "
    "Interim dividend 21 rupees per share declared."
)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


async def _create_or_get_session() -> uuid.UUID:
    """Insert or reuse an analysis_sessions row.

    score_signal writes to signals(session_id FK → analysis_sessions.id),
    so this must exist before the graph runs.
    """
    factory = get_session_factory()
    async with factory() as db:
        repo = AnalysisSessionRepo(db)
        existing = await repo.get_by_thread_id(_THREAD_ID)
        if existing is not None:
            await repo.update_status(_THREAD_ID, "running")
            await db.commit()
            print(f"[setup] Reusing existing session: {existing.id}")
            return existing.id  # type: ignore[return-value]
        session = await repo.create(
            thread_id=_THREAD_ID,
            nse_symbol="INFY",
            trigger_type="manual_test",
            started_at=datetime.now(IST),
            status="running",
        )
        await db.commit()
        print(f"[setup] Created new session: {session.id}")
        return session.id  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# State builder
# ---------------------------------------------------------------------------


def _build_state(session_uuid: uuid.UUID) -> dict[str, Any]:
    """Build the full IndiaMarketState for INFY Q2FY25.

    Live-data fields start empty so the real fetch_market_data and
    fetch_india_context nodes populate them during the run.
    """
    return {
        # Input
        "nse_symbol": "INFY",
        "bse_code": "500209",
        "exchange": "NSE",
        "announcement_type": "quarterly_results",
        "announcement_raw": _ANNOUNCEMENT,
        "s3_key": "",
        "thread_id": _THREAD_ID,
        "session_id": str(session_uuid),
        # Market data — populated by fetch_market_data
        "price_history": {},
        "financials": {},
        "live_quote": {},
        "index_data": {},
        "usd_inr": 0.0,
        # Parsed announcement — populated by parse_announcement
        "parsed_quarterly": None,
        "parsed_board": None,
        "parsed_insider": None,
        "parsed_shp": None,
        # Concall
        "concall_available": False,
        "concall_tone": None,
        "concall_guidance_cr": None,
        "concall_signal_adjustment": None,
        # India context — populated by fetch_india_context
        "nifty_value": 0.0,
        "nifty_change_pct": 0.0,
        "sector_index_change_pct": 0.0,
        "fii_net_flow_cr": 0.0,
        "fii_sentiment": "neutral",
        "usd_inr_context": "stable",
        "market_status": "CLOSED",
        # RAG — populated by retrieve_rag_context + grade_documents
        "retrieved_docs": [],
        "doc_grades": [],
        "used_web_fallback": False,
        # Institutional
        "promoter_pct": None,
        "promoter_trend": None,
        "promoter_pledging_pct": None,
        "promoter_pledging_risk": None,
        "fii_ownership_trend": None,
        # Output — populated by generate_analysis + score_signal
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
        "sebi_disclaimer": "",
        # Meta
        "error": None,
        "retry_count": 0,
        "node_timings": {},
    }


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------


def _print_report(state: dict[str, Any]) -> None:
    print()
    print("=== MarketPulse India — Full Pipeline Test ===")
    print()
    print("STOCK: INFY (Infosys)")
    print("TYPE: Quarterly Results Q2FY25")
    print(_SEP)

    # ── LIVE MARKET DATA ──────────────────────────────────────────────────
    print("LIVE MARKET DATA")
    quote: dict[str, Any] = state.get("live_quote") or {}
    ltp = (
        quote.get("ltp")
        or quote.get("lastPrice")
        or quote.get("current_price")
        or quote.get("close")
        or 0.0
    )
    nifty = state.get("nifty_value") or 0.0
    nifty_chg = state.get("nifty_change_pct") or 0.0
    print(f"  Current Price  : Rs {float(ltp):,.2f}")
    print(f"  Nifty 50       : {nifty:,.0f}  ({nifty_chg:+.2f}%)")
    print(f"  USD/INR        : {state.get('usd_inr', 0.0):.2f}")
    print(f"  Market Status  : {state.get('market_status', '?')}")
    print(_SEP2)

    # ── PARSING ───────────────────────────────────────────────────────────
    print("PARSING")
    parsed: dict[str, Any] = state.get("parsed_quarterly") or {}
    yoy = float(parsed.get("yoy_revenue_growth_pct") or 0.0)
    print(f"  Revenue        : Rs {parsed.get('revenue_cr', 0):,.1f} Cr")
    print(f"  PAT            : Rs {parsed.get('pat_cr', 0):,.1f} Cr")
    print(f"  EPS            : Rs {parsed.get('eps', 0):.2f}")
    print(f"  YoY Growth     : {yoy:+.1f}%")
    print(f"  Verdict        : {parsed.get('beat_or_miss', '?')}")
    print(_SEP2)

    # ── CRAG ─────────────────────────────────────────────────────────────
    print("CRAG")
    docs: list[Any] = state.get("retrieved_docs") or []
    grades: list[Any] = state.get("doc_grades") or []
    relevant = [g for g in grades if isinstance(g, dict) and g.get("relevance") == "relevant"]
    precision = len(relevant) / len(grades) * 100 if grades else 0.0
    print(f"  Docs retrieved : {len(docs)}")
    print(f"  Docs relevant  : {len(relevant)}")
    print(f"  Precision      : {precision:.0f}%")
    print(f"  Web fallback   : {'Yes' if state.get('used_web_fallback') else 'No'}")
    print(_SEP2)

    # ── ANALYSIS ─────────────────────────────────────────────────────────
    print("ANALYSIS")
    summary = state.get("analysis_summary") or ""
    summary_preview = (summary[:120] + "...") if len(summary) > 120 else summary
    print(f"  Verdict        : {state.get('quarter_verdict', '?')}")
    print(f"  Sector outlook : {state.get('sector_outlook', '?')}")
    print(f"  Management tone: n/a")
    print(f"  Sentiment      : n/a")
    if summary_preview:
        print(f"  Summary        : {summary_preview}")
    print(_SEP2)

    # ── KEY POSITIVES ─────────────────────────────────────────────────────
    print("KEY POSITIVES")
    positives: list[Any] = state.get("key_positives") or []
    for p in positives:
        print(f"  + {p}")
    if not positives:
        print("  (none)")
    print(_SEP2)

    # ── KEY RISKS ─────────────────────────────────────────────────────────
    print("KEY RISKS")
    risks: list[Any] = state.get("key_risks") or []
    for r in risks:
        print(f"  - {r}")
    if not risks:
        print("  (none)")
    print(_SEP2)

    # ── SIGNAL ───────────────────────────────────────────────────────────
    print("SIGNAL")
    direction = state.get("signal_direction")
    dir_labels: dict[str, str] = {
        "BUY": "BUY [green circle]",
        "SELL": "SELL [red circle]",
        "HOLD": "HOLD [yellow circle]",
    }
    dir_str = dir_labels.get(direction or "", direction or "?")
    confidence = float(state.get("confidence") or 0.0)
    target = float(state.get("target_price_inr") or 0.0)
    upside = state.get("upside_pct")
    upside_str = f"{upside:+.1f}%" if upside is not None else "n/a"
    print(f"  Direction      : {dir_str}")
    print(f"  Target price   : Rs {target:,.2f}")
    print(f"  Upside         : {upside_str}")
    print(f"  Confidence     : {confidence:.0%}")
    print(f"  Horizon        : {state.get('time_horizon_days')} days")
    print(f"  Rationale      : {state.get('rationale', '')}")
    print(_SEP2)

    # ── NODE TIMINGS ─────────────────────────────────────────────────────
    print("NODE TIMINGS")
    timings: dict[str, float] = state.get("node_timings") or {}
    for node, elapsed in timings.items():
        print(f"  {node:<32}: {round(elapsed * 1000):,}ms")
    if not timings:
        print("  (none recorded)")
    print(_SEP2)

    # ── SEBI DISCLAIMER ───────────────────────────────────────────────────
    print("SEBI DISCLAIMER")
    print(f"  {state.get('sebi_disclaimer', '')}")
    print(_SEP)


# ---------------------------------------------------------------------------
# DB verification
# ---------------------------------------------------------------------------


async def _verify_db(state: dict[str, Any]) -> bool:
    """Query signals table for most recent INFY row and confirm it matches."""
    print("DB VERIFICATION")
    try:
        factory = get_session_factory()
        async with factory() as db:
            repo = SignalRepo(db)
            signals = await repo.get_by_symbol("INFY", limit=1)
            if not signals:
                print("  No INFY signals found in DB")
                print(_SEP)
                return False
            sig = signals[0]
            pipeline_dir = state.get("signal_direction")
            match = sig.direction == pipeline_dir
            created_ist = sig.created_at.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S IST")
            target_str = f"Rs {sig.target_price_inr:,.2f}" if sig.target_price_inr else "n/a"
            print(f"  Most recent INFY signal:")
            print(f"    Direction   : {sig.direction}")
            print(f"    Target      : {target_str}")
            print(f"    Confidence  : {sig.confidence:.0%}")
            print(f"    Created     : {created_ist}")
            print(f"    Matches run : {'Yes' if match else 'No'}")
            print(_SEP)
            return match
    except Exception as exc:
        print(f"  DB query failed: {exc}")
        print(_SEP)
        return False


# ---------------------------------------------------------------------------
# Async runner
# ---------------------------------------------------------------------------


async def _run() -> None:
    # ── Step 2: Ensure analysis_sessions row exists ───────────────────────
    print(f"[setup] Creating analysis_session for thread '{_THREAD_ID}'...")
    try:
        session_uuid = await _create_or_get_session()
    except Exception as exc:
        print(f"[setup] WARNING: DB session creation failed — {exc}")
        session_uuid = uuid.uuid4()

    # ── Step 1: Build initial state ───────────────────────────────────────
    state = _build_state(session_uuid)

    # ── Step 3: Compile graph (no checkpointer for smoke test) and run ────
    print(f"[run] Starting 9-node LangGraph pipeline  (thread: {_THREAD_ID})")
    print(_SEP2)
    final_state: dict[str, Any] = {}
    try:
        graph = build_graph().compile()
        config: dict[str, Any] = {"configurable": {"thread_id": _THREAD_ID}}
        result = await graph.ainvoke(state, config=config)  # type: ignore[arg-type]
        final_state = dict(result)
    except Exception as exc:
        print(f"[run] ERROR: Pipeline raised an exception — {exc}")
        final_state = dict(state)

    # ── Step 4: Formatted report ──────────────────────────────────────────
    _print_report(final_state)

    # ── Step 5: DB verification ───────────────────────────────────────────
    db_save_ok = await _verify_db(final_state)

    # ── PASSED / FAILED ───────────────────────────────────────────────────
    direction = final_state.get("signal_direction")
    disclaimer = final_state.get("sebi_disclaimer") or ""

    if direction is not None and disclaimer and db_save_ok:
        print("FULL PIPELINE TEST PASSED")
    else:
        parts: list[str] = []
        if direction is None:
            parts.append("signal_direction is None")
        if not disclaimer:
            parts.append("sebi_disclaimer missing")
        if not db_save_ok:
            parts.append("signal not saved to DB or direction mismatch")
        print(f"FULL PIPELINE TEST FAILED: {', '.join(parts)}")
    print(_SEP)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    if sys.platform == "win32":
        # psycopg v3 (used by score_signal's DB writes) needs SelectorEventLoop.
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]
        loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
        loop.run_until_complete(_run())
        loop.close()
    else:
        asyncio.run(_run())


if __name__ == "__main__":
    main()
