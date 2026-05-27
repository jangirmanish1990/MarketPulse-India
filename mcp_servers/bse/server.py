"""BSE India MCP server — filings, insider trades, Sensex data, shareholding patterns."""

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


# --------------------------------------------------------------------------- #
# Shareholding pattern — mock data (deterministic fallback)                    #
# --------------------------------------------------------------------------- #

MOCK_SHP_DATA: dict[str, dict[str, Any]] = {
    "RELIANCE": {
        "promoter_pct": 50.33,
        "promoter_pledged_pct": 0.0,
        "fii_pct": 23.45,
        "dii_pct": 14.23,
        "retail_pct": 11.99,
        "quarter": "Sep 2024",
    },
    "TCS": {
        "promoter_pct": 72.19,
        "promoter_pledged_pct": 0.0,
        "fii_pct": 12.34,
        "dii_pct": 10.45,
        "retail_pct": 5.02,
        "quarter": "Sep 2024",
    },
    "INFY": {
        "promoter_pct": 14.77,
        "promoter_pledged_pct": 0.0,
        "fii_pct": 34.56,
        "dii_pct": 35.23,
        "retail_pct": 15.44,
        "quarter": "Sep 2024",
    },
    "HDFCBANK": {
        "promoter_pct": 0.0,
        "promoter_pledged_pct": 0.0,
        "fii_pct": 47.23,
        "dii_pct": 32.45,
        "retail_pct": 20.32,
        "quarter": "Sep 2024",
    },
    "ICICIBANK": {
        "promoter_pct": 0.0,
        "promoter_pledged_pct": 0.0,
        "fii_pct": 43.12,
        "dii_pct": 33.78,
        "retail_pct": 23.10,
        "quarter": "Sep 2024",
    },
    "BAJFINANCE": {
        "promoter_pct": 56.12,
        "promoter_pledged_pct": 0.28,
        "fii_pct": 18.34,
        "dii_pct": 15.67,
        "retail_pct": 9.87,
        "quarter": "Sep 2024",
    },
    "ADANIENT": {
        "promoter_pct": 72.63,
        "promoter_pledged_pct": 15.43,
        "fii_pct": 8.23,
        "dii_pct": 10.45,
        "retail_pct": 8.69,
        "quarter": "Sep 2024",
    },
    "WIPRO": {
        "promoter_pct": 72.89,
        "promoter_pledged_pct": 0.0,
        "fii_pct": 7.34,
        "dii_pct": 11.23,
        "retail_pct": 8.54,
        "quarter": "Sep 2024",
    },
}

DEFAULT_SHP: dict[str, Any] = {
    "promoter_pct": 45.0,
    "promoter_pledged_pct": 0.0,
    "fii_pct": 20.0,
    "dii_pct": 15.0,
    "retail_pct": 20.0,
    "quarter": "Sep 2024",
}


def _pledging_risk(pledged_pct: float) -> str:
    """Classify pledging risk from pledged-shares percentage."""
    if pledged_pct > 20:
        return "high"
    if pledged_pct > 10:
        return "medium"
    if pledged_pct > 0:
        return "low"
    return "none"


def _parse_shp_response(data: Any) -> dict[str, float | str] | None:
    """
    Attempt to parse the BSE ShareHoldingPatterns API response.

    BSE returns a nested structure; field names are inconsistent across
    versions — this handles both the legacy ``Table`` / ``Table1`` layout
    and the newer flat-list style.

    Returns a partial SHP dict on success, None if parsing fails or the
    response looks empty.
    """
    if not data:
        return None

    # Flatten possible envelope shapes
    rows: list[dict[str, Any]] = []
    if isinstance(data, list):
        rows = [r for r in data if isinstance(r, dict)]
    elif isinstance(data, dict):
        for key in ("Table", "Table1", "data", "shareholdingData"):
            val = data.get(key)
            if isinstance(val, list) and val:
                rows = [r for r in val if isinstance(r, dict)]
                break

    if not rows:
        return None

    # We accumulate percentages keyed by BSE category codes / names.
    # BSE uses numeric codes: 1=Promoters, 2=Public, 3=FII, 4=DII, …
    # Newer API uses text labels like "Promoter & Promoter Group", "FII", etc.
    promoter_pct = 0.0
    promoter_pledged_pct = 0.0
    fii_pct = 0.0
    dii_pct = 0.0
    retail_pct = 0.0
    quarter = "Sep 2024"

    for row in rows:
        # Retrieve the percentage value from various possible field names
        raw_pct_str = str(
            row.get("percentHolding")
            or row.get("ShareholdingPct")
            or row.get("Percentage")
            or row.get("totalpct")
            or "0"
        )
        try:
            pct = float(raw_pct_str)
        except ValueError:
            pct = 0.0

        # Category identification
        cat_code = str(
            row.get("categoryCode")
            or row.get("CategoryCode")
            or row.get("GroupCode")
            or ""
        ).strip()
        cat_name = str(
            row.get("categoryName")
            or row.get("CategoryName")
            or row.get("GroupName")
            or row.get("Description")
            or ""
        ).strip().lower()

        # Quarter
        q_raw = str(row.get("quarter") or row.get("Quarter") or "").strip()
        if q_raw:
            quarter = q_raw

        is_promoter = cat_code in ("1", "A") or "promoter" in cat_name
        is_fii = cat_code in ("3", "FII") or "fii" in cat_name or "fpi" in cat_name or "foreign" in cat_name
        is_dii = cat_code in ("4", "DII") or "dii" in cat_name or "mutual fund" in cat_name or "insurance" in cat_name
        is_public = cat_code in ("2", "B") or "public" in cat_name or "retail" in cat_name

        # Pledged shares (only available on promoter rows in some endpoints)
        pledged_raw = str(
            row.get("pledgedSharesPct")
            or row.get("PledgeSharePct")
            or row.get("EncumberedSharesPct")
            or "0"
        )
        try:
            pledged = float(pledged_raw)
        except ValueError:
            pledged = 0.0

        if is_promoter:
            promoter_pct += pct
            if pledged:
                promoter_pledged_pct = pledged
        elif is_fii:
            fii_pct += pct
        elif is_dii:
            dii_pct += pct
        elif is_public:
            retail_pct += pct

    # Sanity-check: if everything is 0 the response was probably empty/malformed
    total = promoter_pct + fii_pct + dii_pct + retail_pct
    if total < 1.0:
        return None

    return {
        "promoter_pct": round(promoter_pct, 2),
        "promoter_pledged_pct": round(promoter_pledged_pct, 2),
        "fii_pct": round(fii_pct, 2),
        "dii_pct": round(dii_pct, 2),
        "retail_pct": round(retail_pct, 2),
        "quarter": quarter,
    }


@mcp.tool()
def get_shareholding_pattern(nse_symbol: str) -> dict[str, Any]:
    """Return the latest shareholding pattern for *nse_symbol*.

    First attempts to fetch live data from the BSE ShareHoldingPatterns API.
    Falls back to deterministic mock data when the live fetch fails or returns
    no usable rows (e.g. outside market hours, scrip not in BSE lookup table).

    Return fields
    -------------
    symbol               : NSE ticker
    bse_code             : BSE scrip code (or "unknown")
    quarter              : Reporting quarter, e.g. "Sep 2024"
    promoter_pct         : Promoter + promoter-group holding (%)
    promoter_pledged_pct : % of promoter shares pledged
    fii_pct              : FII / FPI holding (%)
    dii_pct              : DII holding — MFs + insurance + banks (%)
    retail_pct           : Retail / general-public holding (%)
    source               : "bse_api" | "mock"
    pledging_risk        : "none" | "low" | "medium" | "high"
    """
    sym = nse_symbol.upper()
    bse_code = NSE_TO_BSE.get(sym, "unknown")

    parsed: dict[str, Any] | None = None
    source = "mock"

    # ── 1. Attempt live BSE fetch ──────────────────────────────────────────── #
    if bse_code != "unknown":
        url = (
            f"{_BSE_API}/ShareHoldingPatterns/w"
            f"?scripcode={bse_code}&type="
        )
        try:
            data: Any = bse_get(url)
            parsed = _parse_shp_response(data)
            if parsed is not None:
                source = "bse_api"
                logger.info("get_shareholding_pattern: live data fetched for %s", sym)
        except Exception:
            logger.warning(
                "get_shareholding_pattern: BSE fetch failed for %s, using mock",
                sym,
                exc_info=True,
            )

    # ── 2. Fall back to deterministic mock data ────────────────────────────── #
    if parsed is None:
        parsed = dict(MOCK_SHP_DATA.get(sym, DEFAULT_SHP))
        logger.info(
            "get_shareholding_pattern: returning mock data for %s (source=%s)",
            sym,
            "MOCK_SHP_DATA" if sym in MOCK_SHP_DATA else "DEFAULT_SHP",
        )

    pledged_pct: float = float(parsed.get("promoter_pledged_pct", 0.0))

    return {
        "symbol": sym,
        "bse_code": bse_code,
        "quarter": parsed.get("quarter", "Sep 2024"),
        "promoter_pct": float(parsed.get("promoter_pct", 0.0)),
        "promoter_pledged_pct": pledged_pct,
        "fii_pct": float(parsed.get("fii_pct", 0.0)),
        "dii_pct": float(parsed.get("dii_pct", 0.0)),
        "retail_pct": float(parsed.get("retail_pct", 0.0)),
        "source": source,
        "pledging_risk": _pledging_risk(pledged_pct),
    }


# --------------------------------------------------------------------------- #
# FII / DII flow classification helpers                                        #
# --------------------------------------------------------------------------- #

_FLOW_STRONG_BUYER_THRESHOLD = 3000.0
_FLOW_BUYER_THRESHOLD = 500.0
_FLOW_SELLER_THRESHOLD = -500.0
_FLOW_STRONG_SELLER_THRESHOLD = -3000.0


def _flow_classification(net_cr: float) -> str:
    """Map a net-flow (₹ Crore) to a human-readable classification label."""
    if net_cr > _FLOW_STRONG_BUYER_THRESHOLD:
        return "strong_buyer"
    if net_cr > _FLOW_BUYER_THRESHOLD:
        return "buyer"
    if net_cr >= _FLOW_SELLER_THRESHOLD:
        return "neutral"
    if net_cr >= _FLOW_STRONG_SELLER_THRESHOLD:
        return "seller"
    return "strong_seller"


# Current-week mock values (realistic for a cautious market week)
_MOCK_FII_NET_CR = -823.45   # mild net selling
_MOCK_DII_NET_CR = 1245.67   # moderate net buying (domestic absorption)


@mcp.tool()
def get_fii_dii_flows(sector: str = "all") -> dict[str, Any]:
    """Return indicative FII and DII net equity flows for the current week.

    The *sector* parameter is accepted for API compatibility but the current
    implementation returns aggregate (all-sector) market-wide figures — sector-
    level flow data requires a paid data subscription that is not yet wired up.

    All monetary values are in **₹ Crore** (positive = net buying).

    Return fields
    -------------
    fii_net_cr          : FII / FPI net flow this week (₹ Cr)
    dii_net_cr          : DII net flow this week (₹ Cr)
    fii_classification  : "strong_buyer" | "buyer" | "neutral" | "seller" | "strong_seller"
    dii_classification  : same scale as fii_classification
    sector              : echoed back from the request parameter
    week                : "current"
    source              : always "mock" until real feed is connected
    note                : human-readable caveat string
    """
    fii_net = _MOCK_FII_NET_CR
    dii_net = _MOCK_DII_NET_CR

    return {
        "fii_net_cr": fii_net,
        "dii_net_cr": dii_net,
        "fii_classification": _flow_classification(fii_net),
        "dii_classification": _flow_classification(dii_net),
        "sector": sector,
        "week": "current",
        "source": "mock",
        "note": (
            "Aggregate market-wide figures for the current week. "
            "Sector-level breakdown is not yet available."
        ),
    }


if __name__ == "__main__":
    mcp.run()
