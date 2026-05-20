"""Node: fetch_market_data — call 5 market data sources in parallel."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from langchain_core.runnables import RunnableConfig

from agents.state import IndiaMarketState
from backend.database import get_session_factory
from backend.repositories import AnalysisSessionRepo
from mcp_servers.nse.server import get_announcements, get_live_quote  # noqa: E402
from mcp_servers.yfinance_india.server import (  # noqa: E402
    get_financials,
    get_index_data,
    get_price_history,
    get_usd_inr,
)

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")


def _now_ist() -> datetime:
    return datetime.now(IST)


def _json_default(obj: Any) -> Any:
    """Fallback JSON serialiser — converts datetimes to ISO strings, rest to str."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    return str(obj)


async def fetch_market_data(state: IndiaMarketState, config: RunnableConfig) -> dict[str, Any]:
    """Fetch live market data from nse-mcp and yfinance-india-mcp in parallel.

    Five data sources are fetched concurrently via asyncio.to_thread (the MCP
    tool functions are synchronous). A failure in any single source is logged
    but does not abort the node — empty dicts are used as fallbacks.

    Side effects:
      * Writes a raw JSON snapshot to data/raw/{symbol}/{date}/{type}.json
      * Creates or updates an AnalysisSession row in Postgres
    """
    start = time.monotonic()
    symbol = state["nse_symbol"]
    now = _now_ist()

    print(f"[fetch_market_data] {symbol} — fetching 5 sources in parallel")

    # ── Parallel fetch (return_exceptions keeps gather alive on partial fails) ──
    raw = await asyncio.gather(
        asyncio.to_thread(get_announcements, symbol, 1),
        asyncio.to_thread(get_live_quote, symbol),
        asyncio.to_thread(get_price_history, symbol, "1y", "NSE"),
        asyncio.to_thread(get_financials, symbol, "NSE"),
        asyncio.to_thread(get_index_data),
        return_exceptions=True,
    )
    announcements, live_q, price_h, fin, idx_data = raw

    # ── Per-source error handling ─────────────────────────────────────────
    if isinstance(announcements, Exception):
        logger.warning("[fetch_market_data] get_announcements failed: %s", announcements)
        announcements = []
    if isinstance(live_q, Exception):
        logger.warning("[fetch_market_data] get_live_quote failed: %s", live_q)
        live_q = {}
    if isinstance(price_h, Exception):
        logger.warning("[fetch_market_data] get_price_history failed: %s", price_h)
        price_h = {}
    if isinstance(fin, Exception):
        logger.warning("[fetch_market_data] get_financials failed: %s", fin)
        fin = {}
    if isinstance(idx_data, Exception):
        logger.warning("[fetch_market_data] get_index_data failed: %s", idx_data)
        idx_data = {}

    # ── USD/INR (separate sequential call — avoids extra NSE rate-limit slot) ──
    try:
        fx: dict[str, Any] = await asyncio.to_thread(get_usd_inr)
    except Exception as exc:
        logger.warning("[fetch_market_data] get_usd_inr failed: %s", exc)
        fx = {}

    usd_inr_val = float(fx.get("rate") or state.get("usd_inr") or 83.5)

    # ── Extract Nifty from index_data ─────────────────────────────────────
    nifty: dict[str, Any] = (idx_data or {}).get("nifty50") or {}
    nifty_value = float(nifty.get("value") or 0)
    nifty_change_pct = float(nifty.get("change_pct") or 0)
    ltp = float((live_q or {}).get("ltp") or 0)

    # ── Persist raw snapshot locally (S3 placeholder) ─────────────────────
    date_str = now.strftime("%Y-%m-%d")
    raw_dir = Path("data/raw") / symbol / date_str
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_file = raw_dir / f"{state['announcement_type']}.json"
    try:
        snapshot: dict[str, Any] = {
            "timestamp_ist": now.isoformat(),
            "symbol": symbol,
            "live_quote": live_q,
            "price_history": price_h,
            "financials": fin,
            "index_data": idx_data,
            "usd_inr": usd_inr_val,
            "announcements": announcements,
        }
        raw_file.write_text(
            json.dumps(snapshot, default=_json_default, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning("[fetch_market_data] Raw data save failed: %s", exc)

    # ── Upsert AnalysisSession in Postgres ────────────────────────────────
    try:
        factory = get_session_factory()
        async with factory() as db:
            repo = AnalysisSessionRepo(db)
            existing = await repo.get_by_thread_id(state["thread_id"])
            if existing is None:
                await repo.create(
                    thread_id=state["thread_id"],
                    nse_symbol=symbol,
                    trigger_type=state["announcement_type"],
                    started_at=now,
                    status="running",
                )
            else:
                await repo.update_status(state["thread_id"], "running")
            await db.commit()
    except Exception as exc:
        logger.warning("[fetch_market_data] DB session upsert failed: %s", exc)

    elapsed_ms = round((time.monotonic() - start) * 1000)
    print(
        f"[fetch_market_data] Done in {elapsed_ms}ms — "
        f"quote: ₹{ltp:,.2f}, Nifty: {nifty_value:,.2f}"
    )

    return {
        "live_quote": live_q,
        "price_history": price_h,
        "financials": fin,
        "index_data": idx_data,
        "usd_inr": usd_inr_val,
        "nifty_value": nifty_value,
        "nifty_change_pct": nifty_change_pct,
        "node_timings": {
            **state["node_timings"],
            "fetch_market_data": round(time.monotonic() - start, 3),
        },
    }
