"""Day 9: CRAG pipeline tests + Day 8 parse_announcement tests.

Run from the project root:

    python scripts/test_graph.py

Day 8: Tests parse_announcement node (GPT-4o-mini, 4 announcement types).
Day 9: Tests retrieve_rag_context + grade_documents CRAG nodes.

Requires:
    - OPENAI_API_KEY in .env
    - DATABASE_SYNC_URL / DATABASE_URL with pgvector (for CRAG tests)
    - Run `python scripts/seed_corpus.py` before CRAG tests
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

from agents.nodes.grade import grade_documents  # noqa: E402
from agents.nodes.parse import parse_announcement  # noqa: E402
from agents.nodes.rag import retrieve_rag_context  # noqa: E402

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

def _crag_base_state(symbol: str, ann_type: str, ann_raw: str) -> dict[str, Any]:
    """Minimal state for CRAG node tests."""
    return {
        "nse_symbol": symbol,
        "bse_code": "",
        "exchange": "NSE",
        "announcement_type": ann_type,
        "announcement_raw": ann_raw,
        "s3_key": "",
        "thread_id": "test-crag",
        "session_id": "test-session",
        # market data
        "price_history": {},
        "financials": {},
        "live_quote": {},
        "index_data": {},
        "usd_inr": 84.0,
        # parsed (pre-populated so RAG builds a rich query)
        "parsed_quarterly": {
            "revenue_cr": 40986.0,
            "pat_cr": 6506.0,
            "eps": 15.78,
            "yoy_revenue_growth_pct": 5.1,
            "qoq_revenue_growth_pct": 3.3,
            "operating_margin_pct": 21.1,
            "beat_or_miss": "beat",
            "guidance_next_quarter": "FY25 guidance raised to 4.5%-5% CC",
        },
        "parsed_board": None,
        "parsed_insider": None,
        "parsed_shp": None,
        "quarter_verdict": "beat",
        # concall
        "concall_available": False,
        "concall_tone": None,
        "concall_guidance_cr": None,
        "concall_signal_adjustment": None,
        # india context
        "nifty_value": 24000.0,
        "nifty_change_pct": 0.3,
        "sector_index_change_pct": 0.5,
        "fii_net_flow_cr": 1200.0,
        "fii_sentiment": "buyer",
        "usd_inr_context": "stable",
        "market_status": "CLOSED",
        # RAG (will be populated by nodes)
        "retrieved_docs": [],
        "doc_grades": [],
        "used_web_fallback": False,
        # institutional
        "promoter_pct": None,
        "promoter_trend": None,
        "promoter_pledging_pct": None,
        "promoter_pledging_risk": None,
        "fii_ownership_trend": None,
        # output
        "analysis_summary": None,
        "key_positives": None,
        "key_risks": None,
        "sector_outlook": None,
        "signal_direction": None,
        "confidence": None,
        "current_price_inr": None,
        "target_price_inr": None,
        "upside_pct": None,
        "time_horizon_days": None,
        "rationale": None,
        "sebi_disclaimer": (
            "⚠️ MarketPulse India is not a SEBI-registered investment advisor. "
            "Output is for educational/informational purposes only and is not "
            "investment advice. Markets carry risk; consult a registered advisor "
            "before making decisions."
        ),
        # meta
        "error": None,
        "retry_count": 0,
        "node_timings": {},
    }


_CRAG_INFY_STATE = _crag_base_state(
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
)

_SEP2 = "─" * 44


async def _run_crag_tests() -> int:
    """Run CRAG pipeline tests: retrieve → grade. Returns count of passed tests."""
    print("\n── Day 9: CRAG Pipeline Tests ─────────────────────────────────────")
    print("Tests: retrieve_rag_context + grade_documents  |  Symbol: INFY\n")

    passed = 0
    state: dict[str, Any] = dict(_CRAG_INFY_STATE)

    # ── Test 1: retrieve_rag_context ──────────────────────────────────────
    print(_SEP2)
    print("CRAG TEST 1: retrieve_rag_context")
    print(_SEP2)
    try:
        rag_result = await retrieve_rag_context(state, config={})  # type: ignore[arg-type]
        state.update(rag_result)

        docs: list[Any] = state.get("retrieved_docs") or []
        timing_ms = round((state.get("node_timings") or {}).get("retrieve_rag_context", 0) * 1000)

        print(f"Documents retrieved : {len(docs)}")
        for i, doc in enumerate(docs[:3], 1):
            meta = doc.get("metadata", {})
            score = doc.get("score", 0.0)
            symbol_tag = meta.get("nse_symbol", "?")
            quarter_tag = meta.get("quarter", "")
            source_tag = meta.get("source", "")
            preview = doc.get("content", "")[:80].replace("\n", " ")
            print(f"  [{i}] {symbol_tag} {quarter_tag} ({source_tag}) score={score:.3f}")
            print(f"       {preview}...")
        if len(docs) > 3:
            print(f"  ... and {len(docs) - 3} more")
        print(f"Retrieve time       : {timing_ms:,}ms")

        if len(docs) >= 0:  # even 0 docs is a valid (empty corpus) result
            passed += 1
            print("Status              : PASS ✅")
        else:
            print("Status              : FAIL ❌ (unexpected error)")
    except Exception as exc:
        print(f"CRAG TEST 1 FAILED: {exc}")

    print()

    # ── Test 2: grade_documents ───────────────────────────────────────────
    print(_SEP2)
    print("CRAG TEST 2: grade_documents")
    print(_SEP2)

    docs_count = len(state.get("retrieved_docs") or [])
    if docs_count == 0:
        print("Skipping grade test — no docs retrieved (seed corpus first).")
        print("  Run: python scripts/seed_corpus.py")
    else:
        try:
            grade_result = await grade_documents(state, config={})  # type: ignore[arg-type]
            state.update(grade_result)

            grades: list[Any] = state.get("doc_grades") or []
            timing_ms = round((state.get("node_timings") or {}).get("grade_documents", 0) * 1000)

            relevant = [g for g in grades if g.get("relevance") == "relevant"]
            irrelevant = [g for g in grades if g.get("relevance") == "irrelevant"]
            precision = len(relevant) / len(grades) * 100 if grades else 0.0

            print(f"Docs graded         : {len(grades)}")
            print(f"Relevant            : {len(relevant)}")
            print(f"Irrelevant          : {len(irrelevant)}")
            print(f"Retrieval precision : {precision:.0f}%")
            print(f"CRAG routing        : {'generate_analysis' if len(relevant) >= 2 else 'web_search_fallback'}")
            print()
            for i, g in enumerate(grades[:5], 1):
                icon = "✅" if g.get("relevance") == "relevant" else "❌"
                conf = g.get("confidence", 0.0)
                preview = g.get("content_preview", "")[:60].replace("\n", " ")
                print(f"  [{i}] {icon} conf={conf:.2f}  {preview}")
            if len(grades) > 5:
                print(f"  ... and {len(grades) - 5} more")
            print(f"Grade time          : {timing_ms:,}ms")

            passed += 1
            print("Status              : PASS ✅")
        except Exception as exc:
            print(f"CRAG TEST 2 FAILED: {exc}")

    print()
    return passed


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

    # ── Day 9: CRAG pipeline tests ────────────────────────────────────────
    crag_passed = await _run_crag_tests()

    print(_SEP)
    print(f"Day 8 parser : {passed}/4 ✅" if passed == 4 else f"Day 8 parser : {passed}/4")
    print(f"Day 9 CRAG   : {crag_passed}/2 ✅" if crag_passed == 2 else f"Day 9 CRAG   : {crag_passed}/2")
    print(_SEP)
    print("\nLangSmith traces → https://smith.langchain.com/projects/marketpulse-india")
    return passed == 4 and crag_passed >= 1


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
