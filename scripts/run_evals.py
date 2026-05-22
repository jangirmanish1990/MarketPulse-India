"""Run the MarketPulse India LangSmith evaluation suite.

Builds (or reuses) the marketpulse-india-fy25 dataset on LangSmith,
runs the full 9-node LangGraph pipeline on all 12 FY25 examples, scores
them with 5 evaluators, and prints a PASS/FAIL threshold table.

Usage:
    python scripts/run_evals.py

Required env vars (set in .env):
    OPENAI_API_KEY        — GPT-4o / GPT-4o-mini calls
    LANGCHAIN_API_KEY     — LangSmith tracing + dataset API
    LANGCHAIN_TRACING_V2=true
    LANGCHAIN_PROJECT=marketpulse-india
    DATABASE_URL          — Postgres (for graph nodes that need it)

# Add to GitHub Actions:
# - name: Run LangSmith Evals
#   run: python scripts/run_evals.py
#   env:
#     LANGCHAIN_API_KEY: ${{ secrets.LANGCHAIN_API_KEY }}
#     OPENAI_API_KEY:    ${{ secrets.OPENAI_API_KEY }}
#     DATABASE_URL:      ${{ secrets.DATABASE_URL }}
#     FAIL_IF_BELOW:     "true"
"""

from __future__ import annotations

import asyncio
import logging
import sys
import uuid
from pathlib import Path
from typing import Any

# ── Windows: psycopg3 + asyncpg require SelectorEventLoop ──────────────────
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]

# Force UTF-8 on Windows cp1252 consoles so ₹ in node print() calls don't crash
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ── Make project root importable ────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s  %(message)s")
logger = logging.getLogger(__name__)

from langsmith.evaluation import evaluate  # noqa: E402

from tests.evals.langsmith_evals import (  # noqa: E402
    DATASET_NAME,
    check_thresholds,
    faithfulness,
    india_risk_relevance,
    parser_accuracy,
    run_evaluations,
    sebi_compliance,
    signal_accuracy_vs_nifty,
)

# --------------------------------------------------------------------------- #
# SEBI disclaimer (duplicated here to avoid pulling in FastAPI backend)        #
# --------------------------------------------------------------------------- #

_SEBI_DISCLAIMER = (
    "Warning: MarketPulse India is not a SEBI-registered investment advisor. "
    "Output is for educational and informational purposes only and is not "
    "investment advice. Markets carry risk; consult a registered advisor "
    "before making decisions."
)

# --------------------------------------------------------------------------- #
# Target function                                                               #
# --------------------------------------------------------------------------- #


def _build_eval_state(inputs: dict[str, Any]) -> dict[str, Any]:
    """Build a minimal IndiaMarketState from a LangSmith example's inputs."""
    nse_symbol = str(inputs.get("nse_symbol", "UNKNOWN")).upper()
    thread_id = f"eval-{nse_symbol.lower()}-{uuid.uuid4().hex[:8]}"
    session_id = str(uuid.uuid4())
    return {
        "nse_symbol": nse_symbol,
        "bse_code": "",
        "exchange": "NSE",
        "announcement_type": inputs.get("announcement_type", "quarterly_results"),
        "announcement_raw": str(inputs.get("announcement_raw", "")),
        "s3_key": "",
        "thread_id": thread_id,
        "session_id": session_id,
        "sebi_disclaimer": _SEBI_DISCLAIMER,
        "retry_count": 0,
        "node_timings": {},
        "price_history": {},
        "financials": {},
        "live_quote": {},
        "index_data": {},
        "usd_inr": 0.0,
        "parsed_quarterly": None,
        "parsed_board": None,
        "parsed_insider": None,
        "parsed_shp": None,
        "concall_available": False,
        "concall_tone": None,
        "concall_guidance_cr": None,
        "concall_signal_adjustment": None,
        "nifty_value": 0.0,
        "nifty_change_pct": 0.0,
        "sector_index_change_pct": 0.0,
        "fii_net_flow_cr": 0.0,
        "fii_sentiment": "neutral",
        "usd_inr_context": "stable",
        "market_status": "OPEN",
        "retrieved_docs": [],
        "doc_grades": [],
        "used_web_fallback": False,
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


async def _async_target(inputs: dict[str, Any]) -> dict[str, Any]:
    """Run the full 9-node LangGraph pipeline and return eval-relevant outputs.

    Compiled without a Postgres checkpointer so evals don't require a live DB
    connection. Score_signal's DB write will degrade to a warning log on miss.
    """
    from agents.graph import build_graph

    state = _build_eval_state(inputs)
    nse_symbol: str = state["nse_symbol"]

    try:
        graph = build_graph().compile()  # no checkpointer needed for evals
        config: dict[str, Any] = {"configurable": {"thread_id": state["thread_id"]}}
        final: dict[str, Any] = await graph.ainvoke(state, config=config)  # type: ignore[arg-type]

        return {
            "parsed_quarterly": final.get("parsed_quarterly"),
            "analysis_summary": final.get("analysis_summary"),
            "key_risks": final.get("key_risks"),
            "signal_direction": final.get("signal_direction"),
            "sebi_disclaimer": final.get("sebi_disclaimer", ""),
        }
    except Exception:
        logger.exception("[eval] Pipeline failed for %s", nse_symbol)
        return {"sebi_disclaimer": ""}
    finally:
        # Dispose the async DB engine so the next _sync_target call (with its
        # own fresh event loop) doesn't inherit stale asyncpg connections that
        # are bound to this loop — avoids "attached to a different loop" errors.
        try:
            from backend.database import engine as _db_engine

            await _db_engine.dispose()
        except Exception:
            logger.debug("DB engine dispose skipped (no backend DB in this eval run)")


def _sync_target(inputs: dict[str, Any]) -> dict[str, Any]:
    """Synchronous wrapper for _async_target.

    evaluate() is synchronous; each invocation gets a fresh event loop so
    that parallel calls (max_concurrency > 0) don't share loop state.
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_async_target(inputs))
    finally:
        loop.close()
        asyncio.set_event_loop(None)


# --------------------------------------------------------------------------- #
# Score aggregation                                                             #
# --------------------------------------------------------------------------- #


def _aggregate_scores(experiment_results: Any) -> dict[str, float]:
    """Extract mean score per evaluator from ExperimentResults via to_pandas()."""
    avg_scores: dict[str, float] = {}
    try:
        df = experiment_results.to_pandas()
        for col in df.columns:
            if col.startswith("feedback."):
                metric = col[len("feedback."):]
                try:
                    val = float(df[col].dropna().mean())
                    avg_scores[metric] = round(val, 4)
                except (TypeError, ValueError):
                    avg_scores[metric] = 0.0
        logger.info("Aggregated scores: %s", avg_scores)
    except Exception:
        logger.exception("Failed to aggregate evaluation scores from results DataFrame")
    return avg_scores


# --------------------------------------------------------------------------- #
# Main                                                                          #
# --------------------------------------------------------------------------- #

SEP = "=" * 60
EVALUATORS = [
    parser_accuracy,
    signal_accuracy_vs_nifty,
    faithfulness,
    india_risk_relevance,
    sebi_compliance,
]


def main() -> None:
    print(SEP)
    print("MarketPulse India — LangSmith Evaluation Suite")
    print(SEP)

    # ── 1. Create / verify dataset ─────────────────────────────────────────
    try:
        asyncio.run(run_evaluations("india-v1"))
    except Exception:
        logger.exception("Dataset setup failed")
        print("\nFATAL: Cannot reach LangSmith.")
        print("Check LANGCHAIN_API_KEY is set in .env and LANGCHAIN_TRACING_V2=true")
        sys.exit(1)

    print("\nNumber of examples: 12")
    print(f"Evaluators        : {', '.join(fn.__name__ for fn in EVALUATORS)}")

    # ── 2. Run evaluations ─────────────────────────────────────────────────
    print("\nRunning pipeline on all 12 examples (est. ~5 min)...")
    try:
        experiment_results = evaluate(
            _sync_target,
            data=DATASET_NAME,
            evaluators=EVALUATORS,
            experiment_prefix="india-v1",
            description="MarketPulse India FY25 quarterly results evaluation suite",
        )
    except Exception:
        logger.exception("evaluate() failed")
        print("\nERROR: LangSmith evaluate() call failed.")
        sys.exit(1)

    # ── 3. Aggregate + gate ────────────────────────────────────────────────
    avg_scores = _aggregate_scores(experiment_results)

    passed = asyncio.run(check_thresholds(avg_scores))

    print(f"\n{SEP}")
    if passed:
        print("LangSmith Evals PASSED")
    else:
        print("LangSmith Evals FAILED")
    print(SEP)

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
