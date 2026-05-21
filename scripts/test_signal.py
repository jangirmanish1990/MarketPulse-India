"""Smoke-test for score_signal node — Day 10.

Chains generate_analysis → score_signal with the INFY Q2FY25 scenario.
Run from project root:  python scripts/test_signal.py
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

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from agents.nodes.analysis import generate_analysis  # noqa: E402
from agents.nodes.signal import score_signal  # noqa: E402

_BASE_STATE: dict[str, Any] = {
    "nse_symbol": "INFY",
    "bse_code": "",
    "exchange": "NSE",
    "announcement_type": "quarterly_results",
    "announcement_raw": (
        "Infosys Q2 FY25 Results:\n"
        "Revenue: Rs 40,986 crore, up 5.1% YoY and 3.3% QoQ\n"
        "Net Profit (PAT): Rs 6,506 crore, up 4.7% YoY\n"
        "EPS: Rs 15.78\n"
        "Operating Margin: 21.1%\n"
        "Revenue guidance for FY25 raised to 4.5%-5% in constant currency\n"
        "Deal wins: $2.4 billion TCV in Q2\n"
        "Results beat street estimates of Rs 40,200 Cr revenue"
    ),
    "s3_key": "",
    "thread_id": "test-signal-day10",
    "session_id": "00000000-0000-0000-0000-000000000001",
    "price_history": {},
    "financials": {},
    "index_data": {},
    "live_quote": {"ltp": 1875.5, "current_price": 1875.5, "change_pct": 2.3},
    "usd_inr": 84.12,
    "parsed_quarterly": {
        "revenue_cr": 40986.0,
        "pat_cr": 6506.0,
        "eps": 15.78,
        "yoy_revenue_growth_pct": 5.1,
        "qoq_revenue_growth_pct": 3.3,
        "yoy_pat_growth_pct": 4.7,
        "operating_margin_pct": 21.1,
        "quarter": "Q2FY25",
        "beat_or_miss": "beat",
        "guidance_next_quarter": "FY25 guidance raised to 4.5%-5% CC",
        "key_highlights": ["Guidance upgrade", "Deal wins $2.4B TCV"],
    },
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
    "doc_grades": [
        {
            "relevance": "relevant",
            "confidence": 0.95,
            "content_preview": "Infosys Q2FY25 Quarterly Results: Revenue Rs 40,986 Cr",
            "metadata": {"nse_symbol": "INFY", "quarter": "Q2FY25"},
            "reason": "Same company, same quarter",
        },
        {
            "relevance": "relevant",
            "confidence": 0.85,
            "content_preview": "Wipro Q2FY25 Quarterly Results: Revenue Rs 22,302 Cr (-1.4% YoY)",
            "metadata": {"nse_symbol": "WIPRO", "quarter": "Q2FY25"},
            "reason": "IT peer comparison",
        },
        {
            "relevance": "irrelevant",
            "confidence": 0.90,
            "content_preview": "ICICI Bank Q2FY25: Net Interest Income Rs 20,048 Cr",
            "metadata": {"nse_symbol": "ICICIBANK", "quarter": "Q2FY25"},
            "reason": "Banking sector",
        },
    ],
    "promoter_pct": None,
    "promoter_trend": None,
    "promoter_pledging_pct": None,
    "promoter_pledging_risk": None,
    "fii_ownership_trend": None,
    "analysis_summary": None,
    "key_positives": None,
    "key_risks": None,
    "quarter_verdict": "beat",
    "sector_outlook": None,
    "signal_direction": None,
    "confidence": None,
    "current_price_inr": None,
    "target_price_inr": None,
    "upside_pct": None,
    "time_horizon_days": None,
    "rationale": None,
    "sebi_disclaimer": "",
    "error": None,
    "retry_count": 0,
    "node_timings": {},
}

_SEP = "=" * 56


async def _run() -> None:
    state: dict[str, Any] = dict(_BASE_STATE)

    # ── Stage 1: generate_analysis ──────────────────────────────────────────
    print("\n── Stage 1: generate_analysis ─────────────────────────────────")
    analysis_result = await generate_analysis(state, config={})  # type: ignore[arg-type]
    state.update(analysis_result)

    # ── Stage 2: score_signal ───────────────────────────────────────────────
    print("\n── Stage 2: score_signal ───────────────────────────────────────")
    signal_result = await score_signal(state, config={})  # type: ignore[arg-type]
    state.update(signal_result)

    # ── Output ──────────────────────────────────────────────────────────────
    print()
    print(_SEP)
    print("FINAL SIGNAL OUTPUT  (Day 10 — INFY Q2FY25)")
    print(_SEP)

    direction = state.get("signal_direction", "?")
    confidence = state.get("confidence", 0.0)
    target = state.get("target_price_inr") or 0.0
    upside = state.get("upside_pct")
    horizon = state.get("time_horizon_days")
    current = state.get("current_price_inr") or 0.0
    rationale = state.get("rationale", "")
    verdict = state.get("quarter_verdict", "?")
    sector = state.get("sector_outlook", "?")
    disclaimer = state.get("sebi_disclaimer", "")

    upside_str = f"{upside:+.1f}%" if upside is not None else "n/a"
    dir_icon = {"BUY": "BUY", "SELL": "SELL", "HOLD": "HOLD"}.get(direction, direction)

    print(f"Direction    : {dir_icon}")
    print(f"Confidence   : {confidence:.0%}")
    print(f"Current      : Rs {current:,.2f}")
    print(f"Target       : Rs {target:,.2f}  ({upside_str})")
    print(f"Horizon      : {horizon} days")
    print(f"Verdict      : {verdict}")
    print(f"Sector       : {sector}")
    print(f"Rationale    : {rationale}")
    print()
    print(f"Disclaimer   : {disclaimer}")
    print()

    # Timings
    timings: dict[str, float] = state.get("node_timings") or {}
    analysis_ms = round(timings.get("generate_analysis", 0) * 1000)
    signal_ms = round(timings.get("score_signal", 0) * 1000)
    print(f"Timing       : generate_analysis={analysis_ms:,}ms  score_signal={signal_ms:,}ms")
    print(_SEP)


def main() -> None:
    if sys.platform == "win32":
        loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
        loop.run_until_complete(_run())
        loop.close()
    else:
        asyncio.run(_run())


if __name__ == "__main__":
    main()
