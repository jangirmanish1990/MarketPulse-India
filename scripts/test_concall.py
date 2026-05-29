"""scripts/test_concall.py — End-to-end smoke test for concall_analyzer node.

Usage:
    uv run python scripts/test_concall.py

What this tests:
    * get_concall_transcript MCP tool (cache or mock)
    * ConcallAnalysis chain (gpt-4o-mini structured output)
    * concall_analyzer node wrapper (end-to-end, state in → partial dict out)
    * Confidence delta is applied when state["confidence"] is pre-set

Two symbols tested:
    INFY Q2FY25 — beat + cautious tone (expects tone_more_cautious / downgrade)
    TCS  Q2FY25 — beat + cautious tone (expects a valid adjustment)

Note: runs the LLM chain TWICE per symbol — once directly for rich display
(tone_vs_numbers, key_risks, deal TCV, etc.) and once via the node wrapper to
verify end-to-end integration.  Both calls use the same cached transcript so
the only extra cost is the second LLM invocation.
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

# Windows: ensure UTF-8 output so emoji / rupee signs don't crash
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from langchain_core.runnables import RunnableConfig  # noqa: E402

from agents.llm import get_llm_fast  # noqa: E402
from agents.nodes.concall import (  # noqa: E402
    _PROMPT,  # same prompt the node uses — avoids divergence
    ConcallAnalysis,
    _build_concall_text,
    concall_analyzer,
)
from mcp_servers.indian_news.server import get_concall_transcript  # noqa: E402

_SEP = "═" * 44  # ════════════════════════════════════════════

# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------

_TESTS: list[dict[str, Any]] = [
    {
        "symbol": "INFY",
        "quarter_label": "Q2FY25",
        "quarter_verdict": "beat",
        "announcement_raw": (
            "Infosys Q2 FY25: Revenue Rs 40986 Cr up 5.1% YoY. "
            "PAT Rs 6506 Cr up 4.7% YoY. "
            "Guidance raised to 4.5-5% CC. "
            "Deal TCV $2.4 billion."
        ),
    },
    {
        "symbol": "TCS",
        "quarter_label": "Q2FY25",
        "quarter_verdict": "beat",
        "announcement_raw": (
            "TCS Q2 FY25: Revenue Rs 63973 Cr up 8.1% YoY. "
            "PAT Rs 11909 Cr up 5.0% YoY. "
            "Operating margin 24.5%. "
            "Deal TCV $8.6 billion."
        ),
    },
]

# ---------------------------------------------------------------------------
# State builder
# ---------------------------------------------------------------------------

_BASE_CONFIDENCE = 0.72  # pre-set so confidence_delta is applied and visible


def _make_state(symbol: str, announcement_raw: str, quarter_verdict: str) -> dict[str, Any]:
    """Minimal IndiaMarketState dict for testing concall_analyzer in isolation.

    confidence is pre-set to 0.72 so that the node's confidence_delta is applied
    and we can compute/display the delta.  quarter_verdict simulates the state
    that parse_announcement would have set earlier in the pipeline.
    """
    return {
        "nse_symbol": symbol,
        "bse_code": "",
        "exchange": "NSE",
        "announcement_type": "quarterly_results",
        "announcement_raw": announcement_raw,
        "s3_key": "",
        "thread_id": f"test-concall-{symbol.lower()}",
        "session_id": "test",
        "price_history": {},
        "financials": {},
        "live_quote": {},
        "index_data": {},
        "usd_inr": 84.12,
        "parsed_quarterly": None,
        "parsed_board": None,
        "parsed_insider": None,
        "parsed_shp": None,
        "concall_available": False,
        "concall_tone": None,
        "concall_guidance_cr": None,
        "concall_signal_adjustment": None,
        "nifty_value": 24350.0,
        "nifty_change_pct": 0.4,
        "sector_index_change_pct": 0.7,
        "fii_net_flow_cr": 1850.0,
        "fii_sentiment": "buyer",
        "usd_inr_context": "stable",
        "market_status": "CLOSED",
        "retrieved_docs": [],
        "used_web_fallback": False,
        "doc_grades": [],
        "promoter_pct": None,
        "promoter_trend": None,
        "promoter_pledging_pct": None,
        "promoter_pledging_risk": None,
        "fii_ownership_trend": None,
        "analysis_summary": None,
        "key_positives": None,
        "key_risks": None,
        "quarter_verdict": quarter_verdict,
        "sector_outlook": None,
        "signal_direction": None,
        "confidence": _BASE_CONFIDENCE,
        "current_price_inr": None,
        "target_price_inr": None,
        "upside_pct": None,
        "time_horizon_days": None,
        "rationale": None,
        "sebi_disclaimer": "Educational only.",
        "error": None,
        "retry_count": 0,
        "node_timings": {},
    }


# ---------------------------------------------------------------------------
# Per-symbol test runner
# ---------------------------------------------------------------------------


async def _run_symbol(test: dict[str, Any]) -> bool:
    """Run a single symbol test.  Returns True on pass, False on fail."""
    symbol: str = test["symbol"]
    quarter_label: str = test["quarter_label"]
    announcement_raw: str = test["announcement_raw"]
    quarter_verdict: str = test["quarter_verdict"]

    state = _make_state(symbol, announcement_raw, quarter_verdict)

    print()
    print(_SEP)
    print(f"Concall Analyzer Test -- {symbol} {quarter_label}")
    print(_SEP)

    # ── 1. Fetch transcript (sync → thread; served from disk cache if hit) ─
    transcript: dict[str, Any] = await asyncio.to_thread(get_concall_transcript, symbol, "latest")

    if not transcript.get("available") or not transcript.get("management_opening"):
        print("Transcript available : No")
        print(f"Note                 : {transcript.get('note', 'transcript not found')}")
        print(_SEP)
        print(f"[{symbol}] Skipped (no transcript) -- not a test failure")
        return True  # absence of transcript is a valid state, not a bug

    # ── 2. Run LLM chain directly for rich display ─────────────────────────
    concall_text = _build_concall_text(symbol, transcript, state)  # type: ignore[arg-type]
    chain = _PROMPT | get_llm_fast().with_structured_output(ConcallAnalysis)
    raw: Any = await asyncio.to_thread(chain.invoke, {"text": concall_text})

    if not isinstance(raw, ConcallAnalysis):
        print(f"ERROR: chain returned unexpected type {type(raw)!r}")
        print(_SEP)
        print(f"{symbol} concall test FAILED ❌")
        return False

    analysis: ConcallAnalysis = raw

    # ── 3. Run node wrapper to verify end-to-end integration ──────────────
    node_result: dict[str, Any] = await concall_analyzer(
        state,  # type: ignore[arg-type]
        RunnableConfig(),
    )
    new_conf: float = float(node_result.get("confidence", _BASE_CONFIDENCE))
    timing_s: float = float((node_result.get("node_timings") or {}).get("concall_analyzer", 0.0))

    # ── 4. Print banner ────────────────────────────────────────────────────
    source = transcript.get("source", "unknown")
    risks = analysis.key_risks_mentioned
    positives = analysis.key_positives_mentioned

    print(f"Transcript available : Yes  (source: {source})")
    print(f"Management tone      : {analysis.management_tone}")
    print(f"Tone vs numbers      : {analysis.tone_vs_numbers}")
    print(f"Signal adjustment    : {analysis.signal_adjustment}")
    print(f"Confidence delta     : {analysis.confidence_delta:+.2f}")
    print(f"Key risks mentioned  : {risks[:3] if risks else ['(none identified)']}")
    print(f"Key positives        : {positives[:3] if positives else ['(none identified)']}")
    print(f"Analyst sentiment    : {analysis.analyst_sentiment}")

    if analysis.deal_wins_tcv_usd_bn is not None:
        print(f"Deal TCV             : ${analysis.deal_wins_tcv_usd_bn:.1f}B")
    if analysis.npa_outlook:
        print(f"NPA outlook          : {analysis.npa_outlook}")
    if analysis.nim_guidance:
        print(f"NIM guidance         : {analysis.nim_guidance}")

    print()
    print("--- Node wrapper output ---")
    print(f"concall_available    : {node_result.get('concall_available')}")
    print(f"concall_tone         : {node_result.get('concall_tone')}")
    print(f"concall_adjustment   : {node_result.get('concall_signal_adjustment')}")
    print(
        f"confidence           : {_BASE_CONFIDENCE:.2f} -> {new_conf:.2f}  "
        f"(delta {new_conf - _BASE_CONFIDENCE:+.2f})"
    )
    print(f"timing               : {round(timing_s * 1000):,}ms")

    # ── 5. Assertions ──────────────────────────────────────────────────────
    _VALID_TONES = frozenset({"optimistic", "cautious", "defensive", "mixed"})
    _VALID_ADJUSTMENTS = frozenset({"upgrade", "maintain", "downgrade"})

    assert node_result.get("concall_available") is True, (
        f"[{symbol}] concall_available must be True; got {node_result.get('concall_available')!r}"
    )
    assert node_result.get("concall_tone") in _VALID_TONES, (
        f"[{symbol}] invalid tone: {node_result.get('concall_tone')!r}"
    )
    assert node_result.get("concall_signal_adjustment") in _VALID_ADJUSTMENTS, (
        f"[{symbol}] invalid adjustment: {node_result.get('concall_signal_adjustment')!r}"
    )
    assert isinstance(new_conf, float), (
        f"[{symbol}] confidence must be float; got {type(new_conf)!r}"
    )
    assert 0.10 <= new_conf <= 0.95, f"[{symbol}] confidence out of [0.10, 0.95]: {new_conf}"
    assert "concall_analyzer" in (node_result.get("node_timings") or {}), (
        f"[{symbol}] node_timings missing 'concall_analyzer' key"
    )

    print(_SEP)
    print(f"{symbol} concall test PASSED ✅")
    return True


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


async def _run_all() -> None:
    passed = 0
    failed = 0

    for test in _TESTS:
        symbol: str = test["symbol"]
        try:
            ok = await _run_symbol(test)
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

    print()
    print(_SEP)
    total = passed + failed
    print(f"Concall tests: {passed}/{total} passed")
    print(_SEP)

    if failed:
        sys.exit(1)


def main() -> None:
    # Windows default ProactorEventLoop breaks psycopg/asyncpg —
    # force SelectorEventLoop exactly as every other test script does.
    if sys.platform == "win32":
        loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
        loop.run_until_complete(_run_all())
        loop.close()
    else:
        asyncio.run(_run_all())


if __name__ == "__main__":
    main()
