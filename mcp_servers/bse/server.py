"""BSE India MCP server — filings, insider trades, Sensex data."""

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

import requests  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")

mcp: FastMCP = FastMCP("bse-mcp")

# --------------------------------------------------------------------------- #
# NSE → BSE scrip code mapping (top 30 Nifty stocks)                          #
# --------------------------------------------------------------------------- #

NSE_TO_BSE: dict[str, str] = {
    "RELIANCE": "500325",
    "TCS": "532540",
    "INFY": "500209",
    "HDFCBANK": "500180",
    "ICICIBANK": "532174",
    "HINDUNILVR": "500696",
    "ITC": "500875",
    "SBIN": "500112",
    "BAJFINANCE": "500034",
    "WIPRO": "507685",
    "HCLTECH": "532281",
    "AXISBANK": "532215",
    "KOTAKBANK": "500247",
    "LT": "500510",
    "TITAN": "500114",
    "NESTLEIND": "500790",
    "TECHM": "532755",
    "SUNPHARMA": "524715",
    "DRREDDY": "500124",
    "CIPLA": "500087",
    "ONGC": "500312",
    "NTPC": "532555",
    "POWERGRID": "532898",
    "ADANIENT": "512599",
    "ADANIPORTS": "532921",
    "MARUTI": "532500",
    "TATAMOTORS": "500570",
    "TATASTEEL": "500470",
    "JSWSTEEL": "500228",
    "COALINDIA": "533278",
}

_BSE_API = "https://api.bseindia.com/BseIndiaAPI/api"
_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.bseindia.com",
    "Accept": "application/json, text/plain, */*",
}


def _now_ist() -> datetime:
    return datetime.now(IST)


def _bse_date(dt: datetime) -> str:
    """BSE API expects YYYYMMDD."""
    return dt.strftime("%Y%m%d")


def _parse_bse_dt(raw: str) -> str:
    """Parse BSE datetime strings and return IST ISO string."""
    for fmt in (
        "%d/%m/%Y %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(raw.strip(), fmt)
            return dt.replace(tzinfo=IST).isoformat()
        except ValueError:
            continue
    return raw


def bse_get(url: str) -> Any:
    """Simple GET to BSE API (no cookie session required)."""
    resp = requests.get(url, headers=_HEADERS, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _scrip_code(nse_symbol: str) -> str:
    """Convert NSE symbol to BSE scrip code; raises KeyError if unknown."""
    code = NSE_TO_BSE.get(nse_symbol.upper())
    if code is None:
        raise KeyError(f"No BSE scrip code for NSE symbol '{nse_symbol}'")
    return code


# --------------------------------------------------------------------------- #
# Tools                                                                         #
# --------------------------------------------------------------------------- #


@mcp.tool()
def get_filings(nse_symbol: str, days: int = 7) -> list[dict[str, Any]]:
    """Fetch BSE filings/announcements for *nse_symbol* over the last *days* days.

    Converts the NSE symbol to a BSE scrip code using the built-in lookup table.
    Returns submissions sorted newest-first.
    """
    sym = nse_symbol.upper()
    try:
        scrip = _scrip_code(sym)
    except KeyError:
        logger.warning("Unknown BSE scrip for %s", sym)
        return []

    to_dt = _now_ist()
    from_dt = to_dt - timedelta(days=days)
    url = (
        f"{_BSE_API}/AnnSubCategoryGetData/w"
        f"?strCat=-1&strPrevDate={_bse_date(from_dt)}"
        f"&strScrip={scrip}&strSearch=P"
        f"&strToDate={_bse_date(to_dt)}&strType=C"
    )
    try:
        data: Any = bse_get(url)
        rows: list[dict[str, Any]] = data.get("Table") or data.get("data") or []
        results: list[dict[str, Any]] = []
        for row in rows:
            raw_dt = str(row.get("DT_TM") or row.get("NewsDate") or "")
            results.append(
                {
                    "scrip_code": scrip,
                    "nse_symbol": sym,
                    "filing_type": str(row.get("NEWSSUB") or row.get("SubCatName") or ""),
                    "description": str(row.get("HEADLINE") or row.get("NEWSSUB") or ""),
                    "submission_date_ist": _parse_bse_dt(raw_dt) if raw_dt else "",
                    "attachment_url": str(row.get("ATTACHMENTNAME") or row.get("FILENAME") or ""),
                }
            )
        return results
    except Exception:
        logger.exception("get_filings failed for %s (scrip=%s)", sym, scrip)
        return []


@mcp.tool()
def get_insider_trades(nse_symbol: str) -> list[dict[str, Any]]:
    """Fetch recent insider trading disclosures from BSE for *nse_symbol*.

    Returns trades sorted by trade_date_ist descending. Values in ₹ Crores.
    """
    sym = nse_symbol.upper()
    try:
        scrip = _scrip_code(sym)
    except KeyError:
        logger.warning("Unknown BSE scrip for %s", sym)
        return []

    url = f"{_BSE_API}/InsiderTrading/w?scrip={scrip}"
    try:
        data: Any = bse_get(url)
        rows: list[dict[str, Any]] = data.get("Table") or data.get("data") or []
        results: list[dict[str, Any]] = []
        for row in rows:
            qty = int(row.get("No_of_Shares") or row.get("secAcquiredDisposed") or 0)
            price = float(row.get("Price") or row.get("avgPrice") or 0)
            value_cr = round((qty * price) / 1e7, 4)  # ₹ → ₹ Cr

            raw_dt = str(
                row.get("Date_of_Allotment")
                or row.get("dateOfAcquisitionDisposal")
                or ""
            )
            mode = str(row.get("Mode_of_Aquisition") or row.get("typeOfTransaction") or "")
            results.append(
                {
                    "trader_name": str(
                        row.get("Acquirer_Name") or row.get("personName") or ""
                    ),
                    "designation": str(row.get("Category") or row.get("category") or ""),
                    "trade_type": "buy" if "buy" in mode.lower() or "acq" in mode.lower() else "sell",
                    "quantity": qty,
                    "avg_price_inr": round(price, 2),
                    "value_cr": value_cr,
                    "trade_date_ist": _parse_bse_dt(raw_dt) if raw_dt else "",
                    "holding_pct_after": float(
                        row.get("Shareholding_Post_Acq") or row.get("postShareholdingPercentage") or 0
                    ),
                }
            )
        results.sort(key=lambda x: x["trade_date_ist"], reverse=True)
        return results
    except Exception:
        logger.exception("get_insider_trades failed for %s (scrip=%s)", sym, scrip)
        return []


@mcp.tool()
def get_sensex_data() -> dict[str, Any]:
    """Fetch live BSE Sensex index data.

    Returns current value, change, day range, and 52-week range.
    """
    url = f"{_BSE_API}/SensexData/w"
    try:
        data: Any = bse_get(url)
        # BSE returns either the object directly or nested under a key
        if isinstance(data, list) and data:
            data = data[0]

        curr = float(data.get("currValue") or data.get("Index_Value") or 0)
        prev = float(data.get("prevClose") or data.get("PreviousClose") or curr)
        change = round(curr - prev, 2)
        change_pct = round((change / prev * 100) if prev else 0, 2)

        return {
            "value": round(curr, 2),
            "change": change,
            "change_pct": change_pct,
            "day_high": float(data.get("high") or data.get("High") or 0),
            "day_low": float(data.get("low") or data.get("Low") or 0),
            "year_high": float(data.get("yearHigh") or data.get("fiftytwo_wk_H") or 0),
            "year_low": float(data.get("yearLow") or data.get("fiftytwo_wk_L") or 0),
        }
    except Exception:
        logger.exception("get_sensex_data failed")
        return {}


if __name__ == "__main__":
    mcp.run()
