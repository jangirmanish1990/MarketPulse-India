"""Seed the top 30 NSE stocks into `indian_stocks`.

Idempotent: uses Postgres `ON CONFLICT (nse_symbol) DO UPDATE` so re-running
the script refreshes metadata without duplicating rows.

Usage (from project root, with `.env` populated):
    python scripts/seed_stocks.py
"""

from __future__ import annotations

import asyncio
import logging
from typing import Final

from dotenv import load_dotenv
from sqlalchemy.dialects.postgresql import insert as pg_insert

from backend.database import dispose_engine, get_session_factory
from backend.models import IndianStock

# Load .env so the script works standalone (`python scripts/seed_stocks.py`).
load_dotenv()

logger = logging.getLogger("seed_stocks")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


# ---------------------------------------------------------------------------
# Seed corpus — top 30 NSE stocks. All 30 are marked is_nifty50 AND is_sensex30
# per the Day 2 spec. bse_code values are the canonical 6-digit BSE scrips.
# ---------------------------------------------------------------------------
TOP_30_STOCKS: Final[list[dict[str, object]]] = [
    {
        "nse_symbol": "RELIANCE",
        "bse_code": "500325",
        "company_name": "Reliance Industries Ltd",
        "sector": "Energy",
    },
    {
        "nse_symbol": "TCS",
        "bse_code": "532540",
        "company_name": "Tata Consultancy Services Ltd",
        "sector": "IT",
    },
    {"nse_symbol": "INFY", "bse_code": "500209", "company_name": "Infosys Ltd", "sector": "IT"},
    {
        "nse_symbol": "HDFCBANK",
        "bse_code": "500180",
        "company_name": "HDFC Bank Ltd",
        "sector": "Financials",
    },
    {
        "nse_symbol": "ICICIBANK",
        "bse_code": "532174",
        "company_name": "ICICI Bank Ltd",
        "sector": "Financials",
    },
    {
        "nse_symbol": "HINDUNILVR",
        "bse_code": "500696",
        "company_name": "Hindustan Unilever Ltd",
        "sector": "FMCG",
    },
    {"nse_symbol": "ITC", "bse_code": "500875", "company_name": "ITC Ltd", "sector": "FMCG"},
    {
        "nse_symbol": "SBIN",
        "bse_code": "500112",
        "company_name": "State Bank of India",
        "sector": "Financials",
    },
    {
        "nse_symbol": "BAJFINANCE",
        "bse_code": "500034",
        "company_name": "Bajaj Finance Ltd",
        "sector": "Financials",
    },
    {"nse_symbol": "WIPRO", "bse_code": "507685", "company_name": "Wipro Ltd", "sector": "IT"},
    {
        "nse_symbol": "HCLTECH",
        "bse_code": "532281",
        "company_name": "HCL Technologies Ltd",
        "sector": "IT",
    },
    {
        "nse_symbol": "AXISBANK",
        "bse_code": "532215",
        "company_name": "Axis Bank Ltd",
        "sector": "Financials",
    },
    {
        "nse_symbol": "KOTAKBANK",
        "bse_code": "500247",
        "company_name": "Kotak Mahindra Bank Ltd",
        "sector": "Financials",
    },
    {
        "nse_symbol": "LT",
        "bse_code": "500510",
        "company_name": "Larsen & Toubro Ltd",
        "sector": "Industrials",
    },
    {
        "nse_symbol": "TITAN",
        "bse_code": "500114",
        "company_name": "Titan Company Ltd",
        "sector": "Consumer Discretionary",
    },
    {
        "nse_symbol": "NESTLEIND",
        "bse_code": "500790",
        "company_name": "Nestle India Ltd",
        "sector": "FMCG",
    },
    {
        "nse_symbol": "TECHM",
        "bse_code": "532755",
        "company_name": "Tech Mahindra Ltd",
        "sector": "IT",
    },
    {
        "nse_symbol": "SUNPHARMA",
        "bse_code": "524715",
        "company_name": "Sun Pharmaceutical Industries Ltd",
        "sector": "Healthcare",
    },
    {
        "nse_symbol": "DRREDDY",
        "bse_code": "500124",
        "company_name": "Dr. Reddy's Laboratories Ltd",
        "sector": "Healthcare",
    },
    {
        "nse_symbol": "CIPLA",
        "bse_code": "500087",
        "company_name": "Cipla Ltd",
        "sector": "Healthcare",
    },
    {
        "nse_symbol": "ONGC",
        "bse_code": "500312",
        "company_name": "Oil & Natural Gas Corporation Ltd",
        "sector": "Energy",
    },
    {"nse_symbol": "NTPC", "bse_code": "532555", "company_name": "NTPC Ltd", "sector": "Utilities"},
    {
        "nse_symbol": "POWERGRID",
        "bse_code": "532898",
        "company_name": "Power Grid Corporation of India Ltd",
        "sector": "Utilities",
    },
    {
        "nse_symbol": "ADANIENT",
        "bse_code": "512599",
        "company_name": "Adani Enterprises Ltd",
        "sector": "Conglomerate",
    },
    {
        "nse_symbol": "ADANIPORTS",
        "bse_code": "532921",
        "company_name": "Adani Ports and SEZ Ltd",
        "sector": "Industrials",
    },
    {
        "nse_symbol": "MARUTI",
        "bse_code": "532500",
        "company_name": "Maruti Suzuki India Ltd",
        "sector": "Consumer Discretionary",
    },
    {
        "nse_symbol": "TATAMOTORS",
        "bse_code": "500570",
        "company_name": "Tata Motors Ltd",
        "sector": "Consumer Discretionary",
    },
    {
        "nse_symbol": "TATASTEEL",
        "bse_code": "500470",
        "company_name": "Tata Steel Ltd",
        "sector": "Materials",
    },
    {
        "nse_symbol": "JSWSTEEL",
        "bse_code": "500228",
        "company_name": "JSW Steel Ltd",
        "sector": "Materials",
    },
    {
        "nse_symbol": "COALINDIA",
        "bse_code": "533278",
        "company_name": "Coal India Ltd",
        "sector": "Energy",
    },
]


async def seed_stocks() -> int:
    """Insert or refresh the 30-stock seed corpus. Returns rows touched."""
    factory = get_session_factory()
    touched = 0

    async with factory() as session, session.begin():
        for row in TOP_30_STOCKS:
            values = {
                **row,
                "is_nifty50": True,
                "is_sensex30": True,
            }
            stmt = pg_insert(IndianStock).values(**values)
            # On conflict, refresh mutable metadata fields. Do NOT overwrite
            # `id` or `created_at` — those should stay stable across re-runs.
            stmt = stmt.on_conflict_do_update(
                index_elements=["nse_symbol"],
                set_={
                    "bse_code": stmt.excluded.bse_code,
                    "company_name": stmt.excluded.company_name,
                    "sector": stmt.excluded.sector,
                    "is_nifty50": stmt.excluded.is_nifty50,
                    "is_sensex30": stmt.excluded.is_sensex30,
                },
            )
            await session.execute(stmt)
            touched += 1

    logger.info("Seeded %d stocks (upsert)", touched)
    return touched


async def _amain() -> int:
    try:
        count = await seed_stocks()
    finally:
        await dispose_engine()
    print(f"OK — {count} stocks upserted into indian_stocks")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_amain()))
