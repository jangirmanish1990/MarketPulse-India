"""NSE India MCP server — announcements, live quotes, quarterly results, SHP."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import logging  # noqa: E402
from datetime import datetime, timedelta  # noqa: E402
from typing import Any  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from mcp.server.fastmcp import FastMCP  # noqa: E402

from mcp_servers._cache import cache_get, cache_set  # noqa: E402
from mcp_servers.nse.session import nse_get  # noqa: E402

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

mcp: FastMCP = FastMCP("nse-mcp")

# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #

_NSE_API = "https://www.nseindia.com/api"


def _now_ist() -> datetime:
    return datetime.now(IST)


def _date_str(dt: datetime) -> str:
    return dt.strftime("%d-%m-%Y")


def _parse_nse_dt(raw: str) -> str:
    """Attempt to parse common NSE datetime formats and return ISO string in IST."""
    for fmt in (
        "%d-%b-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
        "%d-%b-%Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(raw.strip(), fmt)
            return dt.replace(tzinfo=IST).isoformat()
        except ValueError:
            continue
    return raw  # return as-is if unparseable


# --------------------------------------------------------------------------- #
# Tools                                                                         #
# --------------------------------------------------------------------------- #


@mcp.tool()
def get_announcements(symbol: str, days: int = 7) -> list[dict[str, Any]]:
    """Fetch corporate announcements for an NSE-listed symbol.

    Returns up to the last *days* calendar days of announcements sorted
    newest-first. Timestamps are in IST (Asia/Kolkata).
    """
    sym = symbol.upper()
    cache_key = f"nse:announcements:{sym}:{days}"
    cached: list[dict[str, Any]] | None = cache_get(cache_key)
    if cached is not None:
        return cached

    to_dt = _now_ist()
    from_dt = to_dt - timedelta(days=days)
    url = (
        f"{_NSE_API}/corp-info"
        f"?symbol={sym}&corpType=announcements"
        f"&from_date={_date_str(from_dt)}&to_date={_date_str(to_dt)}"
    )
    try:
        data = nse_get(url)
        raw: list[dict[str, Any]] = data.get("announcements") or []
        results: list[dict[str, Any]] = []
        for item in raw:
            dt_raw = str(item.get("exchdisstime") or item.get("bcastdttm") or "")
            results.append(
                {
                    "symbol": sym,
                    "subject": str(item.get("subject") or ""),
                    "description": str(item.get("desc") or ""),
                    "exchange_datetime": _parse_nse_dt(dt_raw) if dt_raw else "",
                    "announcement_type": str(item.get("filingType") or ""),
                    "attachment_url": str(item.get("attchmntFile") or ""),
                }
            )
        cache_set(cache_key, results, 300)  # 5 min
        return results
    except Exception:
        logger.exception("get_announcements failed for %s", sym)
        return []


@mcp.tool()
def get_quarterly_results(symbol: str, quarters: int = 4) -> list[dict[str, Any]]:
    """Fetch the last *quarters* quarterly financial results for *symbol*.

    Monetary values are in ₹ Crores.
    """
    sym = symbol.upper()
    cache_key = f"nse:quarterly_results:{sym}"
    cached: list[dict[str, Any]] | None = cache_get(cache_key)
    if cached is not None:
        return cached[:quarters]

    url = f"{_NSE_API}/results-comparator?index=EQ&symbol={sym}"
    try:
        data = nse_get(url)
        raw: list[dict[str, Any]] = data.get("data") or []
        results: list[dict[str, Any]] = []
        for item in raw[:quarters]:
            revenue = float(item.get("revenues") or item.get("totalRevenue") or 0)
            pat = float(item.get("pat") or item.get("netProfit") or 0)
            eps = float(item.get("dilEPS") or item.get("eps") or 0)
            period = str(item.get("reDt") or item.get("period") or "")
            result_date = str(item.get("audStat") or item.get("resultDate") or "")

            # NSE comparator values are in ₹ Cr already for standalone results
            results.append(
                {
                    "symbol": sym,
                    "period": period,
                    "revenue_cr": round(revenue, 2),
                    "pat_cr": round(pat, 2),
                    "eps": round(eps, 2),
                    "yoy_growth_pct": round(
                        float(item.get("yoyGrowth") or item.get("patGrowth") or 0), 2
                    ),
                    "result_date": _parse_nse_dt(result_date) if result_date else "",
                }
            )
        cache_set(cache_key, results, 86400)  # 24 hr
        return results
    except Exception:
        logger.exception("get_quarterly_results failed for %s", sym)
        return []


@mcp.tool()
def get_live_quote(symbol: str) -> dict[str, Any]:
    """Fetch live market quote for an NSE equity symbol.

    Returns LTP, change, circuits, 52-week high/low and market cap (₹ Cr).
    TTL: 30 seconds.
    """
    sym = symbol.upper()
    cache_key = f"nse:live_quote:{sym}"
    cached: dict[str, Any] | None = cache_get(cache_key)
    if cached is not None:
        return cached

    url = f"{_NSE_API}/quote-equity?symbol={sym}"
    try:
        data = nse_get(url)
        pi: dict[str, Any] = data.get("priceInfo") or {}
        whl: dict[str, Any] = pi.get("weekHighLow") or {}
        si: dict[str, Any] = data.get("securityInfo") or {}

        # NSE reports marketCap in ₹ Lakhs → convert to ₹ Cr (÷100)
        mc_lakhs = float(si.get("marketCap") or 0)
        result: dict[str, Any] = {
            "symbol": sym,
            "ltp": float(pi.get("lastPrice") or 0),
            "change": float(pi.get("change") or 0),
            "change_pct": float(pi.get("pChange") or 0),
            "volume": int(pi.get("totalTradedVolume") or pi.get("quantityTraded") or 0),
            "upper_circuit": float(pi.get("upperCP") or 0),
            "lower_circuit": float(pi.get("lowerCP") or 0),
            "week52_high": float(whl.get("max") or 0),
            "week52_low": float(whl.get("min") or 0),
            "market_cap_cr": round(mc_lakhs / 100, 2),
        }
        cache_set(cache_key, result, 30)  # 30 sec
        return result
    except Exception:
        logger.exception("get_live_quote failed for %s", sym)
        return {}


@mcp.tool()
def get_results_calendar(symbols: list[str]) -> list[dict[str, Any]]:
    """Fetch upcoming/recent result dates for *symbols* from the NSE event calendar.

    Returns events sorted by result_date ascending.
    """
    url = f"{_NSE_API}/event-calendar"
    try:
        data = nse_get(url)
        events: list[dict[str, Any]] = data if isinstance(data, list) else (data.get("data") or [])
        sym_upper = {s.upper() for s in symbols}

        results: list[dict[str, Any]] = []
        for ev in events:
            sym = str(ev.get("symbol") or "").upper()
            if sym not in sym_upper:
                continue
            purpose = str(ev.get("purpose") or ev.get("event") or "")
            if "result" not in purpose.lower() and "financial" not in purpose.lower():
                continue
            raw_date = str(ev.get("date") or ev.get("eventDate") or "")
            results.append(
                {
                    "symbol": sym,
                    "company_name": str(ev.get("company") or ev.get("companyName") or ""),
                    "result_date": _parse_nse_dt(raw_date) if raw_date else "",
                    "exchange": "NSE",
                }
            )
        results.sort(key=lambda x: x["result_date"])
        return results
    except Exception:
        logger.exception("get_results_calendar failed for symbols=%s", symbols)
        return []


@mcp.tool()
def get_shareholding_pattern(symbol: str) -> dict[str, Any]:
    """Fetch the latest shareholding pattern for *symbol*.

    Returns promoter, FII, DII, retail percentages and promoter pledge %.
    TTL: 24 hours.
    """
    sym = symbol.upper()
    cache_key = f"nse:shp:{sym}"
    cached: dict[str, Any] | None = cache_get(cache_key)
    if cached is not None:
        return cached

    url = f"{_NSE_API}/corporate-shareholding-pattern?symbol={sym}&isDownload=true"
    try:
        data = nse_get(url)
        # NSE SHP data can be nested; try common structures
        records: list[dict[str, Any]] = []
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            records = data.get("data") or data.get("shareholdingPatterns") or []

        promoter_pct = fii_pct = dii_pct = retail_pct = pledged_pct = 0.0
        quarter = ""

        for rec in records:
            cat = str(rec.get("category") or rec.get("holderCategory") or "").lower()
            pct = float(rec.get("holdingPercent") or rec.get("percentage") or 0)
            if "promoter" in cat:
                promoter_pct = pct
                pledged_pct = float(rec.get("pledgedPercent") or rec.get("pledged") or 0)
                quarter = str(rec.get("quarter") or rec.get("period") or "")
            elif "fii" in cat or "foreign" in cat:
                fii_pct = pct
            elif "dii" in cat or "domestic" in cat or "institution" in cat:
                dii_pct = pct
            elif "public" in cat or "retail" in cat:
                retail_pct = pct

        result: dict[str, Any] = {
            "symbol": sym,
            "quarter": quarter,
            "promoter_pct": round(promoter_pct, 2),
            "fii_pct": round(fii_pct, 2),
            "dii_pct": round(dii_pct, 2),
            "retail_pct": round(retail_pct, 2),
            "promoter_pledged_pct": round(pledged_pct, 2),
        }
        cache_set(cache_key, result, 86400)  # 24 hr
        return result
    except Exception:
        logger.exception("get_shareholding_pattern failed for %s", sym)
        return {}


if __name__ == "__main__":
    mcp.run()
