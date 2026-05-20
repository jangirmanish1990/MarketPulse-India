"""Seed the pgvector store with Indian financial documents for CRAG context.

Run from the project root:

    python scripts/seed_corpus.py

Prerequisites:
    - OPENAI_API_KEY in .env (used for text-embedding-3-small)
    - DATABASE_SYNC_URL or DATABASE_URL in .env (Postgres with pgvector)
    - pgvector extension installed:
          CREATE EXTENSION IF NOT EXISTS vector;
      (Neon has this pre-installed; local docker image must include it)

Seeds 10 blue-chip companies with:
  1. Static FY25 quarterly results (hardcoded, real data)
  2. Live financial snapshots from yfinance
"""

from __future__ import annotations

import sys
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

from db.vector_store import add_documents  # noqa: E402
from mcp_servers.yfinance_india.server import get_financials  # noqa: E402

IST = ZoneInfo("Asia/Kolkata")

# ---------------------------------------------------------------------------
# Static seed documents — real FY25 data, hardcoded for deterministic seeding
# ---------------------------------------------------------------------------
_STATIC_DOCS: list[dict[str, Any]] = [
    {
        "content": (
            "TCS Q2FY25 Quarterly Results:\n"
            "Revenue: ₹63,973 Cr (+8.1% YoY)\n"
            "PAT: ₹12,446 Cr (+5.4% YoY)\n"
            "EPS: ₹33.56\n"
            "Operating Margin: 24.5%\n"
            "Deal wins TCV: $8.6 billion\n"
            "Verdict: beat\n"
            "Highlights: Strong deal momentum, margin stable, "
            "management tone: cautious on discretionary spend recovery\n"
            "Sector: IT"
        ),
        "metadata": {
            "nse_symbol": "TCS",
            "company_name": "Tata Consultancy Services",
            "announcement_type": "quarterly_results",
            "quarter": "Q2FY25",
            "sector": "IT",
            "date_ist": "2024-10-10",
            "source": "static_seed",
        },
    },
    {
        "content": (
            "Infosys Q2FY25 Quarterly Results:\n"
            "Revenue: ₹40,986 Cr (+5.1% YoY, +3.3% QoQ)\n"
            "PAT: ₹6,506 Cr (+4.7% YoY)\n"
            "EPS: ₹15.78\n"
            "Operating Margin: 21.1%\n"
            "Revenue guidance FY25 raised to 4.5%-5% CC\n"
            "Deal wins TCV: $2.4 billion\n"
            "Verdict: beat\n"
            "Highlights: Guidance upgrade positive surprise, "
            "financial services vertical recovering\n"
            "Sector: IT"
        ),
        "metadata": {
            "nse_symbol": "INFY",
            "company_name": "Infosys",
            "announcement_type": "quarterly_results",
            "quarter": "Q2FY25",
            "sector": "IT",
            "date_ist": "2024-10-17",
            "source": "static_seed",
        },
    },
    {
        "content": (
            "HDFC Bank Q2FY25 Quarterly Results:\n"
            "Net Interest Income: ₹30,114 Cr (+10.1% YoY)\n"
            "PAT: ₹16,821 Cr (+5.3% YoY)\n"
            "Gross NPA: 1.36% (improved from 1.33%)\n"
            "Net NPA: 0.41%\n"
            "Credit growth: 7% YoY\n"
            "CASA Ratio: 34.9%\n"
            "Verdict: in-line\n"
            "Highlights: Margins under pressure, deposit "
            "mobilization focus, CEO change digested\n"
            "Sector: Banking"
        ),
        "metadata": {
            "nse_symbol": "HDFCBANK",
            "company_name": "HDFC Bank",
            "announcement_type": "quarterly_results",
            "quarter": "Q2FY25",
            "sector": "Banking",
            "date_ist": "2024-10-19",
            "source": "static_seed",
        },
    },
    {
        "content": (
            "Reliance Industries Q2FY25 Results:\n"
            "Revenue: ₹2,35,481 Cr (+0.6% YoY)\n"
            "PAT: ₹19,323 Cr (+2.2% YoY)\n"
            "EBITDA: ₹45,974 Cr (+2% YoY)\n"
            "Jio Revenue: ₹34,993 Cr (+18% YoY)\n"
            "Retail Revenue: ₹79,762 Cr (+3.5% YoY)\n"
            "O2C Segment: Under pressure due to weak margins\n"
            "Verdict: in-line\n"
            "Sector: Conglomerate"
        ),
        "metadata": {
            "nse_symbol": "RELIANCE",
            "company_name": "Reliance Industries",
            "announcement_type": "quarterly_results",
            "quarter": "Q2FY25",
            "sector": "Conglomerate",
            "date_ist": "2024-10-14",
            "source": "static_seed",
        },
    },
    {
        "content": (
            "Wipro Q2FY25 Quarterly Results:\n"
            "Revenue: ₹22,302 Cr (-1.4% YoY)\n"
            "PAT: ₹3,209 Cr (+21.3% YoY)\n"
            "IT Services Revenue: $2,659 million\n"
            "Operating Margin: 16.8%\n"
            "Q3 guidance: $2,607M-$2,661M (flat to +2% QoQ)\n"
            "Verdict: in-line\n"
            "Highlights: Revenue decline YoY, PAT recovery due to cost actions\n"
            "Sector: IT"
        ),
        "metadata": {
            "nse_symbol": "WIPRO",
            "company_name": "Wipro",
            "announcement_type": "quarterly_results",
            "quarter": "Q2FY25",
            "sector": "IT",
            "date_ist": "2024-10-16",
            "source": "static_seed",
        },
    },
    {
        "content": (
            "ICICI Bank Q2FY25 Quarterly Results:\n"
            "Net Interest Income: ₹20,048 Cr (+9.5% YoY)\n"
            "PAT: ₹11,792 Cr (+14.5% YoY)\n"
            "Gross NPA: 2.15% (improved from 2.16%)\n"
            "Net NPA: 0.42%\n"
            "ROE: 18.3%\n"
            "Verdict: beat\n"
            "Highlights: Strong loan growth, asset quality stable, "
            "retail franchise growing\n"
            "Sector: Banking"
        ),
        "metadata": {
            "nse_symbol": "ICICIBANK",
            "company_name": "ICICI Bank",
            "announcement_type": "quarterly_results",
            "quarter": "Q2FY25",
            "sector": "Banking",
            "date_ist": "2024-10-26",
            "source": "static_seed",
        },
    },
    {
        "content": (
            "Bajaj Finance Q2FY25 Quarterly Results:\n"
            "Net Interest Income: ₹8,838 Cr (+23% YoY)\n"
            "PAT: ₹4,014 Cr (+13% YoY)\n"
            "AUM: ₹3,73,671 Cr (+29% YoY)\n"
            "Gross NPA: 1.06% (vs 0.91% prior)\n"
            "Verdict: in-line\n"
            "Highlights: AUM growth strong but NPA uptick flagged\n"
            "Sector: NBFC"
        ),
        "metadata": {
            "nse_symbol": "BAJFINANCE",
            "company_name": "Bajaj Finance",
            "announcement_type": "quarterly_results",
            "quarter": "Q2FY25",
            "sector": "NBFC",
            "date_ist": "2024-10-29",
            "source": "static_seed",
        },
    },
    {
        "content": (
            "Titan Company Q2FY25 Quarterly Results:\n"
            "Revenue: ₹13,282 Cr (+25% YoY)\n"
            "PAT: ₹896 Cr (-11% YoY)\n"
            "Jewellery Revenue: ₹11,578 Cr (+26% YoY)\n"
            "Watches & Wearables: ₹1,040 Cr (+12% YoY)\n"
            "Verdict: miss\n"
            "Highlights: Revenue strong but PAT hurt by gold price spike\n"
            "Sector: Consumer"
        ),
        "metadata": {
            "nse_symbol": "TITAN",
            "company_name": "Titan Company",
            "announcement_type": "quarterly_results",
            "quarter": "Q2FY25",
            "sector": "Consumer",
            "date_ist": "2024-11-08",
            "source": "static_seed",
        },
    },
    {
        "content": (
            "Nestle India Q3FY25 (Sep) Quarterly Results:\n"
            "Revenue: ₹4,607 Cr (+1.0% YoY)\n"
            "PAT: ₹899 Cr (+6.0% YoY)\n"
            "Domestic Revenue: ₹4,421 Cr\n"
            "EBITDA Margin: 23.0%\n"
            "Verdict: in-line\n"
            "Highlights: Volume growth positive, pricing tailwinds moderate\n"
            "Sector: FMCG"
        ),
        "metadata": {
            "nse_symbol": "NESTLEIND",
            "company_name": "Nestle India",
            "announcement_type": "quarterly_results",
            "quarter": "Q3FY25",
            "sector": "FMCG",
            "date_ist": "2024-10-24",
            "source": "static_seed",
        },
    },
    {
        "content": (
            "Sun Pharmaceutical Q2FY25 Quarterly Results:\n"
            "Revenue: ₹13,238 Cr (+12.2% YoY)\n"
            "PAT: ₹2,972 Cr (+17.0% YoY)\n"
            "US Specialty Revenue: $453M (+15% YoY)\n"
            "India Branded Revenue: ₹4,072 Cr (+11% YoY)\n"
            "EBITDA Margin: 26.7%\n"
            "Verdict: beat\n"
            "Highlights: Specialty portfolio driving US growth, strong India franchise\n"
            "Sector: Pharma"
        ),
        "metadata": {
            "nse_symbol": "SUNPHARMA",
            "company_name": "Sun Pharmaceutical",
            "announcement_type": "quarterly_results",
            "quarter": "Q2FY25",
            "sector": "Pharma",
            "date_ist": "2024-11-13",
            "source": "static_seed",
        },
    },
]

_COMPANIES: list[dict[str, str]] = [
    {"symbol": "TCS", "name": "Tata Consultancy Services", "sector": "IT"},
    {"symbol": "INFY", "name": "Infosys", "sector": "IT"},
    {"symbol": "WIPRO", "name": "Wipro", "sector": "IT"},
    {"symbol": "HDFCBANK", "name": "HDFC Bank", "sector": "Banking"},
    {"symbol": "ICICIBANK", "name": "ICICI Bank", "sector": "Banking"},
    {"symbol": "RELIANCE", "name": "Reliance Industries", "sector": "Conglomerate"},
    {"symbol": "BAJFINANCE", "name": "Bajaj Finance", "sector": "NBFC"},
    {"symbol": "TITAN", "name": "Titan Company", "sector": "Consumer"},
    {"symbol": "NESTLEIND", "name": "Nestle India", "sector": "FMCG"},
    {"symbol": "SUNPHARMA", "name": "Sun Pharmaceutical", "sector": "Pharma"},
]


def _make_financials_doc(company: dict[str, str], fin: dict[str, Any]) -> dict[str, Any]:
    """Format yfinance financials into a seedable document."""
    name = company["name"]
    symbol = company["symbol"]
    sector = company["sector"]
    date_str = datetime.now(IST).strftime("%Y-%m-%d")

    content = (
        f"{name} Latest Financials (yfinance snapshot):\n"
        f"Revenue: ₹{fin.get('revenue_cr', 0):.1f} Cr\n"
        f"PAT: ₹{fin.get('pat_cr', 0):.1f} Cr\n"
        f"EPS: ₹{fin.get('eps', 0):.2f}\n"
        f"PE Ratio: {fin.get('pe_ratio', 0):.1f}x\n"
        f"PB Ratio: {fin.get('pb_ratio', 0):.1f}x\n"
        f"ROE: {fin.get('roe_pct', 0):.1f}%\n"
        f"Market Cap: ₹{fin.get('market_cap_cr', 0):,.0f} Cr\n"
        f"Dividend Yield: {fin.get('dividend_yield_pct', 0):.2f}%\n"
        f"Sector: {sector}"
    )
    return {
        "content": content,
        "metadata": {
            "nse_symbol": symbol,
            "company_name": name,
            "announcement_type": "financials_snapshot",
            "quarter": "latest",
            "sector": sector,
            "date_ist": date_str,
            "source": "yfinance",
        },
    }


def main() -> None:
    total_docs = 0
    live_companies = 0

    # ── 1. Static FY25 seed documents ──────────────────────────────────────
    print(f"Seeding {len(_STATIC_DOCS)} static FY25 documents... ", end="", flush=True)
    add_documents(_STATIC_DOCS)
    total_docs += len(_STATIC_DOCS)
    print("done")

    # ── 2. Live yfinance snapshots ──────────────────────────────────────────
    print()
    for company in _COMPANIES:
        symbol = company["symbol"]
        name = company["name"]
        print(f"Seeding {name} ({symbol})... ", end="", flush=True)

        docs: list[dict[str, Any]] = []
        try:
            fin = get_financials(symbol)
            # Only add if yfinance returned meaningful revenue data
            if fin and float(fin.get("revenue_cr", 0)) > 0:
                docs.append(_make_financials_doc(company, fin))
        except Exception as exc:
            print(f"[yfinance error: {exc}] ", end="")

        if docs:
            add_documents(docs)
            total_docs += len(docs)
            live_companies += 1
            print(f"done ({len(docs)} docs)")
        else:
            print("skipped (no live data)")

    # ── Summary ─────────────────────────────────────────────────────────────
    print()
    print(
        f"Corpus seeded: {total_docs} documents across "
        f"{live_companies} companies (+ {len(_STATIC_DOCS)} static)"
    )


if __name__ == "__main__":
    main()
