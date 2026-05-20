"""yfinance India MCP server — price history, financials, indices, USD/INR."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import logging  # noqa: E402
from typing import Any  # noqa: E402

import yfinance as yf  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402

from mcp_servers._cache import cache_get, cache_set  # noqa: E402

logger = logging.getLogger(__name__)

mcp: FastMCP = FastMCP("yfinance-india-mcp")

# --------------------------------------------------------------------------- #
# Constants                                                                     #
# --------------------------------------------------------------------------- #

_SUFFIX = {"NSE": ".NS", "BSE": ".BO"}
_INDEX_TICKERS = {
    "nifty50": "^NSEI",
    "sensex": "^BSESN",
    "nifty_bank": "^NSEBANK",
    "nifty_it": "^CNXIT",
}
_USD_INR_TICKER = "INR=X"
_CR = 1e7  # 1 Crore = 10,000,000 rupees


def _ticker(symbol: str, exchange: str = "NSE") -> str:
    suffix = _SUFFIX.get(exchange.upper(), ".NS")
    return f"{symbol.upper()}{suffix}"


# --------------------------------------------------------------------------- #
# Tools                                                                         #
# --------------------------------------------------------------------------- #


@mcp.tool()
def get_price_history(
    symbol: str,
    period: str = "1y",
    exchange: str = "NSE",
) -> dict[str, Any]:
    """Fetch OHLCV price history for *symbol* from yfinance.

    *period* follows yfinance conventions: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, ytd, max.
    *exchange*: 'NSE' (default) or 'BSE'.

    Returns dates, close prices, volumes, and periodic return percentages.
    TTL: 5 minutes.
    """
    tk = _ticker(symbol, exchange)
    cache_key = f"yf:price_history:{tk}:{period}"
    cached: dict[str, Any] | None = cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        t = yf.Ticker(tk)
        hist = t.history(period=period)  # type: ignore[no-untyped-call]

        if hist.empty:
            return {"symbol": symbol.upper(), "exchange": exchange, "error": "no data"}

        closes: list[float] = [round(float(c), 2) for c in hist["Close"].tolist()]
        volumes: list[int] = [int(v) for v in hist["Volume"].tolist()]
        dates: list[str] = [str(d.date()) for d in hist.index]

        def _ret(n: int) -> float:
            if len(closes) < n + 1:
                return 0.0
            base = closes[-(n + 1)]
            return round((closes[-1] - base) / base * 100, 2) if base else 0.0

        result: dict[str, Any] = {
            "symbol": symbol.upper(),
            "exchange": exchange.upper(),
            "dates": dates,
            "closes": closes,
            "volumes": volumes,
            "returns_1d_pct": _ret(1),
            "returns_1w_pct": _ret(5),
            "returns_1m_pct": _ret(21),
            "returns_1y_pct": _ret(252),
        }
        cache_set(cache_key, result, 300)  # 5 min
        return result
    except Exception:
        logger.exception("get_price_history failed for %s", tk)
        return {}


@mcp.tool()
def get_financials(symbol: str, exchange: str = "NSE") -> dict[str, Any]:
    """Fetch key financial ratios and metrics for *symbol*.

    Monetary values are in ₹ Crores. Uses yfinance quarterly_financials + info.
    TTL: 24 hours.
    """
    tk = _ticker(symbol, exchange)
    cache_key = f"yf:financials:{tk}"
    cached: dict[str, Any] | None = cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        t = yf.Ticker(tk)
        info: dict[str, Any] = t.info or {}  # type: ignore[assignment]

        revenue_raw = float(info.get("totalRevenue") or 0)
        net_income_raw = float(info.get("netIncomeToCommon") or 0)

        result: dict[str, Any] = {
            "symbol": symbol.upper(),
            "exchange": exchange.upper(),
            "revenue_cr": round(revenue_raw / _CR, 2),
            "pat_cr": round(net_income_raw / _CR, 2),
            "eps": round(float(info.get("trailingEps") or 0), 2),
            "pe_ratio": round(float(info.get("trailingPE") or 0), 2),
            "pb_ratio": round(float(info.get("priceToBook") or 0), 2),
            "roe_pct": round(float(info.get("returnOnEquity") or 0) * 100, 2),
            "roce_pct": round(float(info.get("returnOnAssets") or 0) * 100, 2),
            "debt_to_equity": round(float(info.get("debtToEquity") or 0), 2),
            "market_cap_cr": round(float(info.get("marketCap") or 0) / _CR, 2),
            "dividend_yield_pct": round(float(info.get("dividendYield") or 0) * 100, 2),
        }
        cache_set(cache_key, result, 86400)  # 24 hr
        return result
    except Exception:
        logger.exception("get_financials failed for %s", tk)
        return {}


@mcp.tool()
def get_index_data() -> dict[str, Any]:
    """Fetch live values for Nifty 50, Sensex, Nifty Bank, and Nifty IT.

    Returns current value, change %, day high and day low for each index.
    TTL: 60 seconds.
    """
    cache_key = "yf:index_data"
    cached: dict[str, Any] | None = cache_get(cache_key)
    if cached is not None:
        return cached

    result: dict[str, Any] = {}
    for name, ticker_sym in _INDEX_TICKERS.items():
        try:
            t = yf.Ticker(ticker_sym)
            info: dict[str, Any] = t.info or {}  # type: ignore[assignment]
            prev = float(info.get("previousClose") or info.get("regularMarketPreviousClose") or 0)
            curr = float(
                info.get("regularMarketPrice")
                or info.get("currentPrice")
                or info.get("navPrice")
                or prev
            )
            change_pct = round((curr - prev) / prev * 100, 2) if prev else 0.0
            result[name] = {
                "value": round(curr, 2),
                "change_pct": change_pct,
                "day_high": round(float(info.get("dayHigh") or info.get("regularMarketDayHigh") or 0), 2),
                "day_low": round(float(info.get("dayLow") or info.get("regularMarketDayLow") or 0), 2),
            }
        except Exception:
            logger.exception("get_index_data failed for %s (%s)", name, ticker_sym)
            result[name] = {"value": 0.0, "change_pct": 0.0, "day_high": 0.0, "day_low": 0.0}

    cache_set(cache_key, result, 60)  # 60 sec
    return result


@mcp.tool()
def get_usd_inr() -> dict[str, Any]:
    """Fetch live USD/INR exchange rate from yfinance.

    TTL: 60 seconds.
    """
    cache_key = "yf:usd_inr"
    cached: dict[str, Any] | None = cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        t = yf.Ticker(_USD_INR_TICKER)
        info: dict[str, Any] = t.info or {}  # type: ignore[assignment]
        prev = float(info.get("previousClose") or info.get("regularMarketPreviousClose") or 0)
        curr = float(
            info.get("regularMarketPrice")
            or info.get("currentPrice")
            or prev
        )
        change_pct = round((curr - prev) / prev * 100, 4) if prev else 0.0

        result: dict[str, Any] = {
            "rate": round(curr, 4),
            "change_pct": change_pct,
            "day_high": round(float(info.get("dayHigh") or info.get("regularMarketDayHigh") or 0), 4),
            "day_low": round(float(info.get("dayLow") or info.get("regularMarketDayLow") or 0), 4),
        }
        cache_set(cache_key, result, 60)  # 60 sec
        return result
    except Exception:
        logger.exception("get_usd_inr failed")
        return {}


@mcp.tool()
def get_52wk_data(symbol: str, exchange: str = "NSE") -> dict[str, Any]:
    """Fetch 52-week high/low data and current position for *symbol*.

    *position_pct*: 0 = at 52-week low, 100 = at 52-week high.
    TTL: 1 hour.
    """
    tk = _ticker(symbol, exchange)
    cache_key = f"yf:52wk:{tk}"
    cached: dict[str, Any] | None = cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        t = yf.Ticker(tk)
        info: dict[str, Any] = t.info or {}  # type: ignore[assignment]

        high = float(info.get("fiftyTwoWeekHigh") or 0)
        low = float(info.get("fiftyTwoWeekLow") or 0)
        curr = float(info.get("currentPrice") or info.get("regularMarketPrice") or 0)

        rng = high - low
        position_pct = round((curr - low) / rng * 100, 2) if rng > 0 else 0.0
        away_from_high_pct = round((high - curr) / high * 100, 2) if high > 0 else 0.0
        away_from_low_pct = round((curr - low) / low * 100, 2) if low > 0 else 0.0

        result: dict[str, Any] = {
            "symbol": symbol.upper(),
            "exchange": exchange.upper(),
            "week52_high": round(high, 2),
            "week52_low": round(low, 2),
            "current_price": round(curr, 2),
            "position_pct": position_pct,
            "away_from_high_pct": away_from_high_pct,
            "away_from_low_pct": away_from_low_pct,
        }
        cache_set(cache_key, result, 3600)  # 1 hr
        return result
    except Exception:
        logger.exception("get_52wk_data failed for %s", tk)
        return {}


if __name__ == "__main__":
    mcp.run()
