"""scripts/test_promoter_intelligence.py — smoke test for promoter_intelligence node.

Usage:
    uv run python scripts/test_promoter_intelligence.py

What this tests
---------------
Three symbols that exercise different paths through the node:

1. RELIANCE  — zero pledging, moderate FII sell-pressure
   • pledging_risk = "none"
   • FII mild seller  → confidence nudged down by FII divergence only

2. ADANIENT  — medium pledging (15.43%), high promoter concentration
   • pledging_risk = "medium"
   • Pledging penalty + FII sell-pressure → confidence adjusted more negative

3. HDFCBANK  — zero promoter holding, FII dominant (47.23%)
   • pledging_risk = "none"
   • FII flow is the sole institutional signal

For each symbol the script:
  • Builds a minimal IndiaMarketState with confidence pre-set to 0.72
  • Runs the promoter_intelligence async node end-to-end
  • Prints a formatted result block
  • Asserts the expected pledging_risk and confidence direction
  • Tallies pass/fail and exits 0 or 1

No LLM calls are made — this tests the BSE-mcp helpers + node logic only.
Windows SelectorEventLoop fix is applied automatically.
"""

from __future__ import annotations

import asyncio
import selectors
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Windows: ensure UTF-8 so rupee / emoji chars don't crash
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from langchain_core.runnables import RunnableConfig  # noqa: E402

from agents.nodes.institutional import (  # noqa: E402
    calculate_fii_adjustment,
    calculate_promoter_adjustment,
    promoter_intelligence,
)

_SEP = "─" * 48

# ---------------------------------------------------------------------------
# Confidence baseline — pre-set so the delta is easy to see
# ---------------------------------------------------------------------------

_BASE_CONFIDENCE = 0.72


# ---------------------------------------------------------------------------
# Expected values per symbol (match the BSE mock data)
# ---------------------------------------------------------------------------

_EXPECTED: dict[str, dict[str, Any]] = {
    "RELIANCE": {
        "pledging_risk": "none",
        "promoter_pct": 50.33,
        "pledged_pct": 0.0,
        # FII seller + DII buyer → divergence → fii_adj = -0.04 - 0.03 = -0.07
        # promoter_adj = 0.0 (none/stable)  → total = -0.07
        "expected_total_adj": -0.07,
        "note": "pledging=0%, FII mild seller",
    },
    "ADANIENT": {
        "pledging_risk": "medium",        # 15.43% > 10% → medium
        "promoter_pct": 72.63,
        "pledged_pct": 15.43,
        # promoter_adj = -0.04 (medium/stable)
        # fii_adj = -0.04 (seller) - 0.03 (divergence seller+buyer) = -0.07
        # total = -0.11
        "expected_total_adj": -0.11,
        "note": "pledging=15.43%, high promoter concentration",
    },
    "HDFCBANK": {
        "pledging_risk": "none",          # 0% promoter holding → no pledging
        "promoter_pct": 0.0,
        "pledged_pct": 0.0,
        # promoter_adj = 0.0 (none/stable)
        # fii_adj = -0.07 (seller+divergence)
        # total = -0.07
        "expected_total_adj": -0.07,
        "note": "no promoter, FII dominates (47.23%)",
    },
}

_TESTS: list[str] = ["RELIANCE", "ADANIENT", "HDFCBANK"]


# ---------------------------------------------------------------------------
# Minimal state builder
# ---------------------------------------------------------------------------


def _make_state(symbol: str) -> dict[str, Any]:
    """Return a minimal IndiaMarketState for testing promoter_intelligence.

    Only the fields the node reads/writes need real values; everything else
    gets a safe zero/None/empty default.  confidence is pre-set to 0.72 so
    the node's adjustment is immediately visible.
    """
    return {
        # ── Input ──────────────────────────────────────────────────────────
        "nse_symbol": symbol,
        "bse_code": "",
        "exchange": "NSE",
        "announcement_type": "quarterly_results",
        "announcement_raw": "",
        "s3_key": "",
        "thread_id": f"test-promoter-{symbol.lower()}",
        "session_id": "test-promoter",
        # ── Market data (not used by this node) ────────────────────────────
        "price_history": {},
        "financials": {},
        "live_quote": {},
        "index_data": {},
        "usd_inr": 84.12,
        # ── Parsed announcement (not used by this node) ────────────────────
        "parsed_quarterly": None,
        "parsed_board": None,
        "parsed_insider": None,
        "parsed_shp": None,
        # ── Concall (not used by this node) ────────────────────────────────
        "concall_available": False,
        "concall_tone": None,
        "concall_guidance_cr": None,
        "concall_signal_adjustment": None,
        # ── India context — these may be overwritten by the node ───────────
        "nifty_value": 24350.0,
        "nifty_change_pct": 0.4,
        "sector_index_change_pct": 0.0,
        "fii_net_flow_cr": 0.0,          # node will overwrite
        "fii_sentiment": "neutral",      # node will overwrite
        "usd_inr_context": "stable",
        "market_status": "CLOSED",
        # ── RAG (not used by this node) ────────────────────────────────────
        "retrieved_docs": [],
        "doc_grades": [],
        "used_web_fallback": False,
        # ── Institutional — these are written by this node ─────────────────
        "promoter_pct": None,
        "promoter_trend": None,
        "promoter_pledging_pct": None,
        "promoter_pledging_risk": None,
        "fii_ownership_trend": None,
        # ── Output (not used by this node) ────────────────────────────────
        "analysis_summary": None,
        "key_positives": None,
        "key_risks": None,
        "quarter_verdict": None,
        "sector_outlook": None,
        "signal_direction": None,
        "confidence": _BASE_CONFIDENCE,   # pre-set so adjustment is visible
        "current_price_inr": None,
        "target_price_inr": None,
        "upside_pct": None,
        "time_horizon_days": None,
        "rationale": None,
        "sebi_disclaimer": "For educational purposes only.",
        # ── Meta ───────────────────────────────────────────────────────────
        "error": None,
        "retry_count": 0,
        "node_timings": {},
    }


# ---------------------------------------------------------------------------
# Per-symbol test runner
# ---------------------------------------------------------------------------


async def _run_symbol(symbol: str) -> bool:
    """Run promoter_intelligence for one symbol.  Returns True on pass."""
    expected = _EXPECTED[symbol]
    state: dict[str, Any] = _make_state(symbol)

    print()
    print(_SEP)
    print(f"  Promoter Intelligence Test — {symbol}")
    print(f"  ({expected['note']})")
    print(_SEP)

    # ── 1. Run the node ──────────────────────────────────────────────────── #
    result: dict[str, Any] = await promoter_intelligence(
        state,  # type: ignore[arg-type]
        RunnableConfig(),
    )

    # ── 2. Extract written fields ─────────────────────────────────────────── #
    promoter_pct: float = float(result.get("promoter_pct") or 0.0)
    pledged_pct: float = float(result.get("promoter_pledging_pct") or 0.0)
    pledging_risk: str = str(result.get("promoter_pledging_risk") or "none")
    promoter_trend: str = str(result.get("promoter_trend") or "stable")
    fii_sentiment: str = str(result.get("fii_sentiment") or "neutral")
    fii_net_cr: float = float(result.get("fii_net_flow_cr") or 0.0)
    fii_ownership_trend: str = str(result.get("fii_ownership_trend") or "—")
    new_conf: float = float(result.get("confidence") or _BASE_CONFIDENCE)
    elapsed_ms: int = int((result.get("node_timings") or {}).get("promoter_intelligence", 0))

    # ── 3. Recompute expected adjustment for display ──────────────────────── #
    promoter_adj = calculate_promoter_adjustment(pledging_risk, promoter_trend)
    # DII classification comes from the flows — parse it out of the trend string
    # e.g. "FII seller | DII buyer"  →  dii_class = "buyer"
    dii_class = "neutral"
    if "|" in fii_ownership_trend:
        dii_part = fii_ownership_trend.split("|")[-1].strip()   # "DII buyer"
        dii_class = dii_part.split()[-1] if dii_part.split() else "neutral"
    fii_adj = calculate_fii_adjustment(fii_sentiment, dii_class)
    total_adj = round(promoter_adj + fii_adj, 3)
    conf_delta = round(new_conf - _BASE_CONFIDENCE, 3)

    # Describe what drove the adjustment
    if promoter_adj < 0 and fii_adj < 0:
        adj_note = "pledging + FII selling"
    elif promoter_adj < 0:
        adj_note = f"pledging risk ({pledging_risk})"
    elif fii_adj < 0:
        adj_note = "FII selling"
    elif fii_adj > 0:
        adj_note = "FII buying"
    else:
        adj_note = "neutral"

    # ── 4. Print formatted result block ──────────────────────────────────── #
    print(f"Promoter holding : {promoter_pct:.2f}%")
    print(f"Pledged shares   : {pledged_pct:.2f}%")
    print(f"Pledging risk    : {pledging_risk}")
    print(f"FII sentiment    : {fii_sentiment}")
    print(f"FII net flow     : {fii_net_cr:+,.0f} Cr")
    print(f"DII sentiment    : {dii_class}")
    print(f"Institutional    : {fii_ownership_trend}")
    print()
    print(f"Promoter adj     : {promoter_adj:+.3f}")
    print(f"FII adj          : {fii_adj:+.3f}")
    print(f"Total adj        : {total_adj:+.3f}")
    print(f"Confidence adj   : {conf_delta:+.3f}  ({adj_note})")
    print(f"Confidence       : {_BASE_CONFIDENCE:.2f} → {new_conf:.3f}")
    print(f"Elapsed          : {elapsed_ms}ms")

    # ── 5. Assertions ─────────────────────────────────────────────────────── #
    errors: list[str] = []

    # 5a. Pledging risk must match expected
    if pledging_risk != expected["pledging_risk"]:
        errors.append(
            f"pledging_risk: expected {expected['pledging_risk']!r}, "
            f"got {pledging_risk!r}"
        )

    # 5b. Promoter pct must be written and match expected (within tolerance)
    if abs(promoter_pct - expected["promoter_pct"]) > 0.01:
        errors.append(
            f"promoter_pct: expected {expected['promoter_pct']:.2f}, "
            f"got {promoter_pct:.2f}"
        )

    # 5c. Pledged pct must match
    if abs(pledged_pct - expected["pledged_pct"]) > 0.01:
        errors.append(
            f"promoter_pledging_pct: expected {expected['pledged_pct']:.2f}, "
            f"got {pledged_pct:.2f}"
        )

    # 5d. Confidence must have been adjusted (node wrote to it)
    if result.get("confidence") is None:
        errors.append("confidence was None — node did not write it")
    elif result.get("confidence") == _BASE_CONFIDENCE and total_adj != 0.0:
        errors.append(
            f"confidence unchanged at {_BASE_CONFIDENCE} despite "
            f"total_adj={total_adj:+.3f}"
        )

    # 5e. Total adjustment must match expected (within float tolerance)
    exp_adj: float = expected["expected_total_adj"]
    if abs(total_adj - exp_adj) > 0.001:
        errors.append(
            f"total_adj: expected {exp_adj:+.3f}, got {total_adj:+.3f}"
        )

    # 5f. Confidence direction: for all three symbols FII is selling → negative
    if total_adj < 0 and new_conf >= _BASE_CONFIDENCE:
        errors.append(
            f"confidence should have decreased (adj={total_adj:+.3f}) "
            f"but stayed at {new_conf:.3f}"
        )

    # 5g. node_timings must be recorded
    if "promoter_intelligence" not in (result.get("node_timings") or {}):
        errors.append("node_timings missing 'promoter_intelligence' key")

    # ── 6. Report ─────────────────────────────────────────────────────────── #
    print()
    if errors:
        for err in errors:
            print(f"  ✗ FAIL: {err}")
        print(_SEP)
        print(f"  {symbol} FAILED ❌")
        return False
    else:
        print(f"  {symbol} PASSED ✅")
        return True


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


async def _run_all() -> None:
    passed = 0
    failed = 0

    for symbol in _TESTS:
        try:
            ok = await _run_symbol(symbol)
            if ok:
                passed += 1
            else:
                failed += 1
        except AssertionError as exc:
            print(f"\n[{symbol}] ASSERTION FAILED: {exc}")
            failed += 1
        except Exception as exc:
            print(f"\n[{symbol}] UNEXPECTED ERROR: {exc!r}")
            import traceback

            traceback.print_exc()
            failed += 1

    total = passed + failed
    print()
    print(_SEP)
    print(f"  Promoter Intelligence: {passed}/{total} tests passed")
    print(_SEP)

    if failed:
        sys.exit(1)


def main() -> None:
    """Entry point.

    Forces SelectorEventLoop on Windows — the default ProactorEventLoop
    breaks asyncio.to_thread when threads use selectors internally, and
    also breaks psycopg/asyncpg if those are imported during the run.
    """
    if sys.platform == "win32":
        loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
        loop.run_until_complete(_run_all())
        loop.close()
    else:
        asyncio.run(_run_all())


if __name__ == "__main__":
    main()
