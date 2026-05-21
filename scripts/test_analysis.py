"""Quick smoke-test for generate_analysis node — Day 10."""

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

_STATE: dict[str, Any] = {
    "nse_symbol": "INFY",
    "bse_code": "",
    "exchange": "NSE",
    "announcement_type": "quarterly_results",
    "announcement_raw": (
        "Infosys Q2 FY25 Results:\n"
        "Revenue: ₹40,986 crore, up 5.1% YoY and 3.3% QoQ\n"
        "Net Profit (PAT): ₹6,506 crore, up 4.7% YoY\n"
        "EPS: ₹15.78\n"
        "Operating Margin: 21.1%\n"
        "Revenue guidance for FY25 raised to 4.5%-5% in constant currency\n"
        "Deal wins: $2.4 billion TCV in Q2\n"
        "Results beat street estimates of ₹40,200 Cr revenue"
    ),
    "s3_key": "",
    "thread_id": "test-analysis",
    "session_id": "test",
    "price_history": {},
    "financials": {},
    "index_data": {},
    "live_quote": {"current_price": 1875.5, "change_pct": 2.3},
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
            "content_preview": "Infosys Q2FY25 Quarterly Results: Revenue: ₹40,986 Cr",
            "metadata": {"nse_symbol": "INFY", "quarter": "Q2FY25"},
            "reason": "Same company, same quarter",
        },
        {
            "relevance": "relevant",
            "confidence": 0.85,
            "content_preview": "Wipro Q2FY25 Quarterly Results: Revenue: ₹22,302 Cr (-1.4% YoY)",
            "metadata": {"nse_symbol": "WIPRO", "quarter": "Q2FY25"},
            "reason": "IT peer comparison",
        },
        {
            "relevance": "irrelevant",
            "confidence": 0.90,
            "content_preview": "ICICI Bank Q2FY25: Net Interest Income ₹20,048 Cr",
            "metadata": {"nse_symbol": "ICICIBANK", "quarter": "Q2FY25"},
            "reason": "Banking sector — different vertical",
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
    "sebi_disclaimer": "Educational only.",
    "error": None,
    "retry_count": 0,
    "node_timings": {},
}

_SEP = "=" * 52


async def _run() -> None:
    result = await generate_analysis(_STATE, config={})  # type: ignore[arg-type]

    summary = result.get("analysis_summary", "")
    positives: list[str] = result.get("key_positives") or []
    risks: list[str] = result.get("key_risks") or []
    verdict = result.get("quarter_verdict", "")
    sector = result.get("sector_outlook", "")
    timing_s: float = (result.get("node_timings") or {}).get("generate_analysis", 0.0)

    print()
    print(_SEP)
    print("generate_analysis OUTPUT  (Day 10)")
    print(_SEP)
    print(f"Summary      : {summary}")
    print()
    print("Key Positives:")
    for p in positives:
        print(f"  + {p}")
    print()
    print("Key Risks:")
    for r in risks:
        print(f"  - {r}")
    print()
    print(f"Verdict      : {verdict}")
    print(f"Sector       : {sector}")
    print(f"Timing       : {round(timing_s * 1000):,}ms")
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
