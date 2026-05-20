"""Day 8: parse_announcement node tests — GPT-4o-mini structured extraction.

Run from the project root:

    python scripts/test_graph.py

Requires OPENAI_API_KEY in .env.
Calls GPT-4o-mini 4 times (one per announcement type). No NSE/DB calls.
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

from agents.nodes.parse import parse_announcement  # noqa: E402

# --------------------------------------------------------------------------- #
# Minimal state template — only fields parse_announcement reads/writes         #
# --------------------------------------------------------------------------- #

def _base_state(symbol: str, ann_type: str, ann_raw: str) -> dict[str, Any]:
    return {
        "nse_symbol": symbol,
        "announcement_type": ann_type,
        "announcement_raw": ann_raw,
        "parsed_quarterly": None,
        "parsed_board": None,
        "parsed_insider": None,
        "parsed_shp": None,
        "quarter_verdict": None,
        "node_timings": {},
    }


# --------------------------------------------------------------------------- #
# Test scenarios                                                                #
# --------------------------------------------------------------------------- #

_TESTS: list[dict[str, Any]] = [
    _base_state(
        "INFY",
        "quarterly_results",
        """
Infosys Q2 FY25 Results:
Revenue: ₹40,986 crore, up 5.1% YoY and 3.3% QoQ
Net Profit (PAT): ₹6,506 crore, up 4.7% YoY
EPS: ₹15.78
Operating Margin: 21.1%
Revenue guidance for FY25 raised to 4.5%-5% in constant currency
Deal wins: $2.4 billion TCV in Q2
Results beat street estimates of ₹40,200 Cr revenue
""",
    ),
    _base_state(
        "TCS",
        "board_meeting",
        """
TCS Board Meeting Outcome:
The Board of Directors has declared an interim dividend of ₹10 per share
of face value ₹1 each for FY2025.
Record date: October 18, 2024
The board also approved a share buyback of ₹17,000 crore at ₹4,150 per share.
""",
    ),
    _base_state(
        "HDFCBANK",
        "insider_trade",
        """
Disclosure under SEBI (Prohibition of Insider Trading) Regulations:
Name: Sashidhar Jagdishan
Designation: MD & CEO
Type of Security: Equity Shares
Type of Transaction: Buy
Number of shares: 10,000
Price: ₹1,642.50 per share
Total Value: ₹1.64 Crore
Date of transaction: October 15, 2024
Shareholding after transaction: 0.0021%
""",
    ),
    _base_state(
        "RELIANCE",
        "shareholding",
        """
Shareholding Pattern for quarter ended September 2024:
Promoter & Promoter Group: 50.33% (previous quarter: 50.33%)
Foreign Portfolio Investors: 23.45% (previous: 24.12%)
Domestic Mutual Funds: 5.67%
Insurance Companies: 3.21%
Other DIIs: 1.45%
Retail & Others: 15.89%
Promoter shares pledged: 0%
""",
    ),
]

_SEP = "═" * 44


def _print_quarterly(symbol: str, d: dict[str, Any], elapsed_ms: int) -> None:
    verdict_icon = "✅" if d["beat_or_miss"] == "beat" else ("❌" if d["beat_or_miss"] == "miss" else "➖")
    print(_SEP)
    print(f"TEST 1: {symbol} Quarterly Results")
    print(_SEP)
    print(f"Revenue     : ₹{d['revenue_cr']:,.1f} Cr")
    print(f"PAT         : ₹{d['pat_cr']:,.1f} Cr")
    print(f"EPS         : ₹{d['eps']:.2f}")
    print(f"YoY Growth  : {d['yoy_revenue_growth_pct']:+.1f}%")
    print(f"QoQ Growth  : {d['qoq_revenue_growth_pct']:+.1f}%")
    if d.get("operating_margin_pct") is not None:
        print(f"Op. Margin  : {d['operating_margin_pct']:.1f}%")
    print(f"Verdict     : {d['beat_or_miss']} {verdict_icon}")
    if d.get("guidance_next_quarter"):
        print(f"Guidance    : {d['guidance_next_quarter']}")
    print(f"Parse time  : {elapsed_ms:,}ms")


def _print_board(symbol: str, d: dict[str, Any], elapsed_ms: int) -> None:
    sentiment_icon = "✅" if "positive" in d["sentiment"] else "➖"
    print(_SEP)
    print(f"TEST 2: {symbol} Board Meeting")
    print(_SEP)
    if d.get("dividend_per_share_inr") is not None:
        print(f"Dividend    : ₹{d['dividend_per_share_inr']:.2f}/share ({d.get('dividend_type', '—')})")
    if d.get("record_date"):
        print(f"Record date : {d['record_date']}")
    if d.get("buyback_total_cr") is not None:
        print(f"Buyback     : ₹{d['buyback_total_cr']:,.0f} Cr @ ₹{d['buyback_price_inr']:,.0f}/share")
    if d.get("other_decisions"):
        for dec in d["other_decisions"]:
            print(f"Decision    : {dec}")
    print(f"Sentiment   : {d['sentiment']} {sentiment_icon}")
    print(f"Parse time  : {elapsed_ms:,}ms")


def _print_insider(symbol: str, d: dict[str, Any], elapsed_ms: int) -> None:
    trade_icon = "🟢" if d["trade_type"] == "buy" else "🔴"
    print(_SEP)
    print(f"TEST 3: {symbol} Insider Trade")
    print(_SEP)
    print(f"Trader      : {d['trader_name']} ({d['designation']})")
    print(f"Type        : {d['trade_type'].upper()} {trade_icon}")
    print(f"Shares      : {d['quantity']:,} @ ₹{d['avg_price_inr']:,.2f}")
    print(f"Value       : ₹{d['value_cr']:.2f} Cr")
    if d.get("holding_pct_after") is not None:
        print(f"Holding     : {d['holding_pct_after']:.4f}% after trade")
    print(f"Sentiment   : {d['sentiment']} ✅")
    print(f"Parse time  : {elapsed_ms:,}ms")


def _print_shp(symbol: str, d: dict[str, Any], elapsed_ms: int) -> None:
    pledged = d.get("promoter_pledged_pct") or 0.0
    risk = d.get("pledging_risk", "none")
    risk_icon = "✅" if risk == "none" else ("⚠️" if risk in ("low", "medium") else "🚨")
    fii_change = d.get("fii_change")
    fii_str = f"{d['fii_pct']:.2f}%"
    if fii_change is not None:
        fii_str += f" ({fii_change:+.2f}%)"
    promoter_change = d.get("promoter_change")
    promoter_str = f"{d['promoter_pct']:.2f}%"
    if promoter_change is not None:
        promoter_str += f" ({promoter_change:+.2f}%)" if promoter_change != 0 else " (no change)"
    dii_total = d["dii_pct"]
    print(_SEP)
    print(f"TEST 4: {symbol} Shareholding")
    print(_SEP)
    print(f"Promoter    : {promoter_str}")
    print(f"FII         : {fii_str}")
    print(f"DII         : {dii_total:.2f}%")
    print(f"Retail      : {d['retail_pct']:.2f}%")
    print(f"Pledging    : {pledged:.0f}% — Risk: {risk} {risk_icon}")
    print(f"Parse time  : {elapsed_ms:,}ms")


# --------------------------------------------------------------------------- #
# Async runner                                                                  #
# --------------------------------------------------------------------------- #

async def _run() -> bool:
    print("\n── MarketPulse India — parse_announcement tests (Day 8) ──────────")
    print("Model: gpt-4o-mini  |  Tests: 4  |  No NSE/DB calls\n")

    passed = 0

    for i, state in enumerate(_TESTS, 1):
        symbol = state["nse_symbol"]
        ann_type = state["announcement_type"]
        try:
            result = await parse_announcement(state, config={})  # type: ignore[arg-type]
        except Exception as exc:
            print(f"\nTest {i} ({symbol} {ann_type}) FAILED: {exc}\n")
            continue

        timings: dict[str, float] = result.get("node_timings") or {}
        elapsed_ms = round(timings.get("parse_announcement", 0) * 1000)

        if ann_type == "quarterly_results":
            d = result.get("parsed_quarterly")
            if d:
                _print_quarterly(symbol, d, elapsed_ms)
                passed += 1
            else:
                print(f"Test {i} ({symbol} quarterly_results) — parse returned None ❌")

        elif ann_type == "board_meeting":
            d = result.get("parsed_board")
            if d:
                _print_board(symbol, d, elapsed_ms)
                passed += 1
            else:
                print(f"Test {i} ({symbol} board_meeting) — parse returned None ❌")

        elif ann_type == "insider_trade":
            d = result.get("parsed_insider")
            if d:
                _print_insider(symbol, d, elapsed_ms)
                passed += 1
            else:
                print(f"Test {i} ({symbol} insider_trade) — parse returned None ❌")

        elif ann_type == "shareholding":
            d = result.get("parsed_shp")
            if d:
                _print_shp(symbol, d, elapsed_ms)
                passed += 1
            else:
                print(f"Test {i} ({symbol} shareholding) — parse returned None ❌")

        print()

    print(_SEP)
    if passed == 4:
        print("All 4 parser tests PASSED ✅")
    else:
        print(f"{passed}/4 parser tests passed")
    print(_SEP)
    print("\nLangSmith traces → https://smith.langchain.com/projects/marketpulse-india")
    return passed == 4


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
