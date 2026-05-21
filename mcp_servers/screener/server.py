"""Screener.in MCP server — 10-year financials, peer comparison, key ratios.

Scrapes https://www.screener.in/company/{SYMBOL}/consolidated/ using
requests + BeautifulSoup. Redis-caches raw HTML and parsed results for
24 hours to minimise HTTP traffic; falls back gracefully if Redis is down.

Rate-limit: 2-second delay between actual HTTP requests (cache hits skip it).
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import requests  # noqa: E402
from bs4 import BeautifulSoup, Tag  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402

from mcp_servers._cache import cache_get, cache_set  # noqa: E402

logger = logging.getLogger(__name__)

mcp: FastMCP = FastMCP("screener-mcp")

# --------------------------------------------------------------------------- #
# Constants                                                                     #
# --------------------------------------------------------------------------- #

_CONSOLIDATED_URL = "https://www.screener.in/company/{symbol}/consolidated/"
_STANDALONE_URL = "https://www.screener.in/company/{symbol}/"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}
_TTL = 86_400  # 24 hours — data changes at end of trading day
_REQUEST_DELAY = 2.0  # seconds between HTTP requests

_last_request: float = 0.0


# --------------------------------------------------------------------------- #
# Private helpers                                                               #
# --------------------------------------------------------------------------- #


def _wait() -> None:
    """Enforce minimum gap between HTTP requests."""
    global _last_request
    elapsed = time.monotonic() - _last_request
    if elapsed < _REQUEST_DELAY:
        time.sleep(_REQUEST_DELAY - elapsed)
    _last_request = time.monotonic()


def _fetch_html(symbol: str) -> str | None:
    """Return Screener.in page HTML for *symbol*, hitting Redis cache first.

    Tries the consolidated URL; falls back to standalone if consolidated
    returns a non-200 response.
    """
    sym = symbol.upper()
    cache_key = f"screener:html:{sym}"
    cached: Any = cache_get(cache_key)
    if isinstance(cached, str) and cached:
        return cached

    _wait()
    for url_tpl in (_CONSOLIDATED_URL, _STANDALONE_URL):
        url = url_tpl.format(symbol=sym)
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=15)
            if resp.status_code == 200:
                html = resp.text
                cache_set(cache_key, html, _TTL)
                return html
            logger.debug("Screener.in HTTP %d for %s at %s", resp.status_code, sym, url)
        except Exception:
            logger.exception("Screener.in request failed for %s", sym)
    return None


def _get_soup(symbol: str) -> BeautifulSoup | None:
    html = _fetch_html(symbol)
    return BeautifulSoup(html, "html.parser") if html else None


def _num(text: str) -> float:
    """Parse Indian-formatted string (₹, commas, %, Cr.) to float."""
    try:
        cleaned = (
            str(text)
            .replace("₹", "")
            .replace(",", "")
            .replace("%", "")
            .replace("Cr.", "")
            .replace("Cr", "")
            .strip()
        )
        if cleaned in ("", "-", "--", "N/A", "NA"):
            return 0.0
        return float(cleaned)
    except ValueError:
        return 0.0


def _section_table(
    soup: BeautifulSoup,
    section_id: str,
) -> tuple[list[str], dict[str, list[float]]]:
    """Extract (column_headers, {row_label: [values]}) from a data-table section."""
    section = soup.find("section", {"id": section_id})
    if not isinstance(section, Tag):
        return [], {}

    table = section.find("table")
    if not isinstance(table, Tag):
        return [], {}

    headers: list[str] = []
    thead = table.find("thead")
    if isinstance(thead, Tag):
        first_tr = thead.find("tr")
        if isinstance(first_tr, Tag):
            ths = first_tr.find_all(["th", "td"])
            headers = [th.get_text(strip=True) for th in ths[1:]]

    rows: dict[str, list[float]] = {}
    tbody = table.find("tbody")
    if isinstance(tbody, Tag):
        for tr in tbody.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            label = cells[0].get_text(strip=True)
            if not label:
                continue
            rows[label] = [_num(c.get_text(strip=True)) for c in cells[1:]]

    return headers, rows


def _row(data: dict[str, list[float]], *candidates: str) -> list[float]:
    """Return the first row whose label (case-insensitive) contains any candidate."""
    for cand in candidates:
        low = cand.lower()
        for label, values in data.items():
            if low in label.lower():
                return values
    return []


def _pick(
    values: list[float],
    all_headers: list[str],
    wanted_headers: list[str],
) -> list[float]:
    """Select values corresponding to *wanted_headers* from *all_headers*."""
    out: list[float] = []
    for h in wanted_headers:
        try:
            i = all_headers.index(h)
            out.append(values[i] if i < len(values) else 0.0)
        except ValueError:
            out.append(0.0)
    return out


def _mar_headers(headers: list[str], n: int = 10) -> list[str]:
    """Return the last *n* column headers that look like 'Mar YYYY'."""
    return [h for h in headers if h.startswith("Mar ")][-n:]


# --------------------------------------------------------------------------- #
# Tools                                                                         #
# --------------------------------------------------------------------------- #


@mcp.tool()
def get_10yr_financials(symbol: str) -> dict[str, Any]:
    """Scrape 10-year financial history from Screener.in.

    Combines data from the Profit & Loss, Ratios, and Balance Sheet sections.
    Returns revenue, PAT, EPS, OPM%, ROE%, ROCE%, D/E, and dividend payout
    aligned to the same set of annual columns ('Mar YYYY').

    All monetary values are in ₹ Crores. TTL: 24 hours.
    """
    sym = symbol.upper()
    cache_key = f"screener:10yr:{sym}"
    cached: dict[str, Any] | None = cache_get(cache_key)
    if cached is not None:
        return cached

    soup = _get_soup(sym)
    if soup is None:
        return {"symbol": sym, "error": "failed to fetch page", "source": "screener.in"}

    try:
        # ── Profit & Loss ─────────────────────────────────────────────────
        pl_heads, pl_rows = _section_table(soup, "profit-loss")
        years = _mar_headers(pl_heads, 10)

        def _pl(*cands: str) -> list[float]:
            return _pick(_row(pl_rows, *cands), pl_heads, years)

        revenue = _pl("Sales +", "Sales", "Net Sales", "Revenue")
        pat = _pl("Net Profit +", "Net Profit", "PAT", "Profit after tax")
        eps = _pl("EPS in Rs", "EPS", "Earnings Per Share")
        opm = _pl("OPM %", "OPM%", "Operating Profit Margin")
        dividend = _pl("Dividend Payout", "Dividend %", "Dividend")

        # ── Annual Ratios ─────────────────────────────────────────────────
        r_heads, r_rows = _section_table(soup, "ratios")
        r_years = _mar_headers(r_heads, 20)  # get more so we can match

        def _r(*cands: str) -> list[float]:
            vals = _row(r_rows, *cands)
            # Align to same year set as P&L
            aligned = _pick(vals, r_heads, r_years)
            # Now pick by matching year label
            out: list[float] = []
            for yr in years:
                try:
                    idx = r_years.index(yr)
                    out.append(aligned[idx] if idx < len(aligned) else 0.0)
                except ValueError:
                    out.append(0.0)
            return out

        # ROCE comes from the annual ratios section (the only ratio there beside working capital)
        roce = _r("ROCE %", "Return on capital employed", "ROCE%")

        # ── Balance Sheet for D/E and ROE denominator ─────────────────────
        bs_heads, bs_rows = _section_table(soup, "balance-sheet")
        bs_years = _mar_headers(bs_heads, 20)

        def _bs(*cands: str) -> list[float]:
            vals = _row(bs_rows, *cands)
            aligned = _pick(vals, bs_heads, bs_years)
            out: list[float] = []
            for yr in years:
                try:
                    idx = bs_years.index(yr)
                    out.append(aligned[idx] if idx < len(aligned) else 0.0)
                except ValueError:
                    out.append(0.0)
            return out

        borrowings = _bs("Borrowings", "Total Borrowings", "Total Debt")
        equity_cap = _bs("Equity Capital", "Share Capital", "Paid-up Capital")
        reserves = _bs("Reserves", "Retained Earnings", "Surplus")

        de: list[float] = []
        roe: list[float] = []
        for i in range(len(years)):
            borrow = borrowings[i] if i < len(borrowings) else 0.0
            eq = (equity_cap[i] if i < len(equity_cap) else 0.0) + (
                reserves[i] if i < len(reserves) else 0.0
            )
            de.append(round(borrow / eq, 2) if eq > 0 else 0.0)
            # ROE = Net Profit / Shareholders' Equity x 100
            profit = pat[i] if i < len(pat) else 0.0
            roe.append(round(profit / eq * 100, 1) if eq > 0 else 0.0)

        n = len(years)
        result: dict[str, Any] = {
            "symbol": sym,
            "years": years,
            "revenue_cr": revenue[:n],
            "pat_cr": pat[:n],
            "eps": eps[:n],
            "opm_pct": opm[:n],
            "roe_pct": roe[:n],
            "roce_pct": roce[:n],
            "debt_to_equity": de[:n],
            "dividend_pct": dividend[:n],
            "source": "screener.in",
        }
        cache_set(cache_key, result, _TTL)
        return result

    except Exception:
        logger.exception("get_10yr_financials failed for %s", sym)
        return {"symbol": sym, "error": "parse error", "source": "screener.in"}


@mcp.tool()
def get_peer_comparison(symbol: str) -> dict[str, Any]:
    """Scrape peer companies from the Screener.in industry sector page.

    Screener.in renders its peer comparison table via JavaScript, so this tool
    discovers the company's industry URL from the company page, then fetches the
    Screener market/industry page which is server-rendered and contains a table
    of companies with market cap, P/E, and dividend yield.

    Returns up to 15 companies from the same industry. TTL: 24 hours.
    """
    sym = symbol.upper()
    cache_key = f"screener:peers:{sym}"
    cached: dict[str, Any] | None = cache_get(cache_key)
    if cached is not None:
        return cached

    soup = _get_soup(sym)
    if soup is None:
        return {"symbol": sym, "peers": [], "error": "failed to fetch page", "source": "screener.in"}

    try:
        # ── Step 1: Extract industry URL from the peers section ────────────
        # The peers section contains a breadcrumb: Broad Sector > Sector > Industry
        # We want the most specific (Industry-level) link.
        sector_url: str | None = None
        peers_section = soup.find("section", {"id": "peers"})
        if isinstance(peers_section, Tag):
            for a in peers_section.find_all("a", href=True):
                href = str(a.get("href", ""))
                title = str(a.get("title", "")).lower()
                if href.startswith("/market/") and "industry" in title:
                    sector_url = f"https://www.screener.in{href}"
                    # keep iterating to take the last (most specific) match

        if not sector_url:
            return {
                "symbol": sym,
                "peers": [],
                "error": "industry URL not found in company page",
                "source": "screener.in",
            }

        # ── Step 2: Fetch sector/industry listing page ─────────────────────
        sector_id = sector_url.rstrip("/").rsplit("/", 1)[-1]
        sector_cache_key = f"screener:sector:{sector_id}"
        sector_html: Any = cache_get(sector_cache_key)
        if not isinstance(sector_html, str) or not sector_html:
            _wait()
            try:
                resp = requests.get(sector_url, headers=_HEADERS, timeout=15)
                if resp.status_code != 200:
                    return {
                        "symbol": sym,
                        "peers": [],
                        "error": f"sector page HTTP {resp.status_code}",
                        "source": "screener.in",
                    }
                sector_html = resp.text
                cache_set(sector_cache_key, sector_html, _TTL)
            except Exception:
                logger.exception("sector page fetch failed for %s", sym)
                return {
                    "symbol": sym,
                    "peers": [],
                    "error": "sector page fetch failed",
                    "source": "screener.in",
                }

        # ── Step 3: Parse sector table ─────────────────────────────────────
        sector_soup = BeautifulSoup(sector_html, "html.parser")
        table = sector_soup.find("table")
        if not isinstance(table, Tag):
            return {
                "symbol": sym,
                "peers": [],
                "error": "sector table not found",
                "source": "screener.in",
            }

        col_labels: list[str] = []
        header_skip = 0  # number of tbody rows to skip (used as header)
        thead = table.find("thead")
        if isinstance(thead, Tag):
            header_row = thead.find("tr")
            if isinstance(header_row, Tag):
                col_labels = [th.get_text(strip=True) for th in header_row.find_all(["th", "td"])]

        # Screener.in sector pages embed the header as the first tbody row
        if not col_labels:
            tbody_tmp = table.find("tbody")
            if isinstance(tbody_tmp, Tag):
                first_tr = tbody_tmp.find("tr")
                if isinstance(first_tr, Tag):
                    col_labels = [td.get_text(strip=True) for td in first_tr.find_all(["th", "td"])]
                    header_skip = 1

        def _ci(*candidates: str) -> int:
            for cand in candidates:
                low = cand.lower()
                for i, lbl in enumerate(col_labels):
                    if low in lbl.lower():
                        return i
            return -1

        name_i = _ci("name")
        cap_i = _ci("mar cap", "market cap", "m.cap")
        pe_i = _ci("p/e", "pe ")

        def _cv(row_cells: list[Tag], col: int) -> float:
            if col < 0 or col >= len(row_cells):
                return 0.0
            return _num(row_cells[col].get_text(strip=True))

        peers: list[dict[str, Any]] = []
        tbody = table.find("tbody")
        if not isinstance(tbody, Tag):
            return {"symbol": sym, "peers": peers, "source": "screener.in"}

        all_tbody_rows = tbody.find_all("tr")
        for tr in all_tbody_rows[header_skip:]:
            cells = tr.find_all(["td", "th"])
            if not cells or name_i < 0 or name_i >= len(cells):
                continue
            peer_name = cells[name_i].get_text(strip=True)
            # Skip serial-number or empty rows
            if not peer_name or peer_name.replace(".", "").strip().isdigit():
                continue
            peers.append(
                {
                    "name": peer_name,
                    "market_cap_cr": _cv(cells, cap_i),
                    "pe_ratio": _cv(cells, pe_i),
                    "roe_pct": 0.0,  # not in sector listing; use get_key_ratios per company
                    "revenue_cr": 0.0,  # not in sector listing
                }
            )

        result: dict[str, Any] = {
            "symbol": sym,
            "peers": peers[:15],
            "source": "screener.in",
        }
        cache_set(cache_key, result, _TTL)
        return result

    except Exception:
        logger.exception("get_peer_comparison failed for %s", sym)
        return {"symbol": sym, "peers": [], "error": "parse error", "source": "screener.in"}


@mcp.tool()
def get_key_ratios(symbol: str) -> dict[str, Any]:
    """Scrape current key valuation and profitability ratios from Screener.in.

    Returns Market Cap, P/E, P/B, Dividend Yield, ROCE, ROE, Face Value, and
    Book Value. All monetary values in ₹ Crores. TTL: 24 hours.
    """
    sym = symbol.upper()
    cache_key = f"screener:ratios:{sym}"
    cached: dict[str, Any] | None = cache_get(cache_key)
    if cached is not None:
        return cached

    soup = _get_soup(sym)
    if soup is None:
        return {"symbol": sym, "error": "failed to fetch page", "source": "screener.in"}

    try:
        # The top-ratios section uses <li> items with id attributes like
        # "database-mktcap", "database-stock-pe", etc.
        # Also try matching by the name span text for forward compatibility.
        ratio_section = soup.find(id="top-ratios")
        if not isinstance(ratio_section, Tag):
            # Fallback: look for any section/div with "company-ratios" class
            ratio_section = soup.find(class_="company-ratios")

        ratios: dict[str, float] = {}

        if isinstance(ratio_section, Tag):
            for li in ratio_section.find_all("li"):
                # Prefer id-based lookup
                li_id = li.get("id", "")
                name_span = li.find("span", class_="name")
                val_span = li.find(
                    "span",
                    class_=lambda c: c and ("value" in c or "number" in c),  # type: ignore[arg-type]
                )
                if not isinstance(val_span, Tag):
                    # Try sibling span / any span with numeric content
                    spans = li.find_all("span")
                    for sp in reversed(spans):
                        if isinstance(sp, Tag) and sp.get_text(strip=True):
                            val_span = sp
                            break

                value = _num(val_span.get_text(strip=True)) if isinstance(val_span, Tag) else 0.0
                name_text = (
                    name_span.get_text(strip=True).lower() if isinstance(name_span, Tag) else ""
                )

                # Map by id first (most reliable), then by name text
                if "mktcap" in li_id or "market cap" in name_text:
                    ratios["market_cap_cr"] = value
                elif "current-price" in li_id or "current price" in name_text:
                    ratios["current_price"] = value
                elif "high" in li_id and "low" in li_id:
                    pass  # skip high/low
                elif "stock-pe" in li_id or "p/e" in name_text or "stock p/e" in name_text:
                    ratios["pe_ratio"] = value
                elif "book-value" in li_id or "book value" in name_text:
                    ratios["book_value_inr"] = value
                elif "dividend-yield" in li_id or "dividend yield" in name_text:
                    ratios["div_yield_pct"] = value
                elif "roce" in li_id or "roce" in name_text:
                    ratios["roce_pct"] = value
                elif "roe" in li_id or "roe" in name_text:
                    ratios["roe_pct"] = value
                elif "face-value" in li_id or "face value" in name_text:
                    ratios["face_value_inr"] = value

        # P/B = Current Price / Book Value
        pb = 0.0
        if ratios.get("current_price") and ratios.get("book_value_inr"):
            pb = round(ratios["current_price"] / ratios["book_value_inr"], 2)

        result: dict[str, Any] = {
            "symbol": sym,
            "market_cap_cr": ratios.get("market_cap_cr", 0.0),
            "pe_ratio": ratios.get("pe_ratio", 0.0),
            "pb_ratio": pb,
            "div_yield_pct": ratios.get("div_yield_pct", 0.0),
            "roce_pct": ratios.get("roce_pct", 0.0),
            "roe_pct": ratios.get("roe_pct", 0.0),
            "face_value_inr": ratios.get("face_value_inr", 0.0),
            "book_value_inr": ratios.get("book_value_inr", 0.0),
            "source": "screener.in",
        }
        cache_set(cache_key, result, _TTL)
        return result

    except Exception:
        logger.exception("get_key_ratios failed for %s", sym)
        return {"symbol": sym, "error": "parse error", "source": "screener.in"}


if __name__ == "__main__":
    mcp.run()
