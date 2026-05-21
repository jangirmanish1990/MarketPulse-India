"""Screener.in MCP smoke-test — run against INFY.

Usage:
    python scripts/test_screener.py

Fetches 10-year financials, peer comparison, and key ratios for INFY.
Prints a formatted summary to stdout. Expects network access to screener.in.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Windows cp1252 consoles can't print ₹ — force UTF-8
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Make project root importable when run directly
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcp_servers.screener.server import (
    get_10yr_financials,
    get_key_ratios,
    get_peer_comparison,
)

SYMBOL = "INFY"
SEP = "=" * 60


def _pct(v: object) -> str:
    return f"{v:.1f}%" if isinstance(v, float) else str(v)


def _cr(v: object) -> str:
    return f"₹{v:,.0f} Cr" if isinstance(v, (int, float)) else str(v)


def test_10yr_financials() -> None:
    print(f"\n{SEP}")
    print(f"10-Year Financials — {SYMBOL}")
    print(SEP)

    data = get_10yr_financials(SYMBOL)

    if data.get("error"):
        print(f"  ERROR: {data['error']}")
        return

    years = data.get("years", [])
    revenue = data.get("revenue_cr", [])
    pat = data.get("pat_cr", [])
    opm = data.get("opm_pct", [])
    roe = data.get("roe_pct", [])
    eps = data.get("eps", [])

    header = f"{'Year':<12} {'Revenue':>14} {'PAT':>12} {'OPM%':>8} {'ROE%':>8} {'EPS':>8}"
    print(header)
    print("-" * len(header))

    for i, yr in enumerate(years):
        rev = revenue[i] if i < len(revenue) else 0.0
        p = pat[i] if i < len(pat) else 0.0
        op = opm[i] if i < len(opm) else 0.0
        r = roe[i] if i < len(roe) else 0.0
        e = eps[i] if i < len(eps) else 0.0
        print(f"{yr:<12} {rev:>14,.0f} {p:>12,.0f} {op:>7.1f}% {r:>7.1f}% {e:>8.2f}")

    if revenue:
        first, last = revenue[0], revenue[-1]
        if first > 0:
            cagr = ((last / first) ** (1 / max(len(years) - 1, 1)) - 1) * 100
            print(f"\nRevenue CAGR ({years[0]}-{years[-1]}): {cagr:.1f}%")

    print(f"Source: {data.get('source', '?')}")


def test_peer_comparison() -> None:
    print(f"\n{SEP}")
    print(f"Peer Comparison — {SYMBOL}")
    print(SEP)

    data = get_peer_comparison(SYMBOL)

    if data.get("error") and not data.get("peers"):
        print(f"  ERROR: {data['error']}")
        return

    peers = data.get("peers", [])
    if not peers:
        print("  No peers found.")
        return

    header = f"{'Company':<22} {'Mkt Cap (Cr)':>14} {'P/E':>8} {'ROE%':>8} {'Revenue Cr':>12}"
    print(header)
    print("-" * len(header))

    for p in peers[:10]:  # top 10
        name = str(p.get("name", ""))[:22]
        cap = p.get("market_cap_cr", 0.0)
        pe = p.get("pe_ratio", 0.0)
        roe = p.get("roe_pct", 0.0)
        rev = p.get("revenue_cr", 0.0)
        print(f"{name:<22} {cap:>14,.0f} {pe:>8.1f} {roe:>7.1f}% {rev:>12,.0f}")

    print(f"Source: {data.get('source', '?')}")


def test_key_ratios() -> None:
    print(f"\n{SEP}")
    print(f"Key Ratios — {SYMBOL}")
    print(SEP)

    data = get_key_ratios(SYMBOL)

    if data.get("error"):
        print(f"  ERROR: {data['error']}")
        return

    fields = [
        ("Market Cap", "market_cap_cr", "₹{:,.0f} Cr"),
        ("P/E Ratio", "pe_ratio", "{:.2f}x"),
        ("P/B Ratio", "pb_ratio", "{:.2f}x"),
        ("Dividend Yield", "div_yield_pct", "{:.2f}%"),
        ("ROCE", "roce_pct", "{:.1f}%"),
        ("ROE", "roe_pct", "{:.1f}%"),
        ("Face Value", "face_value_inr", "₹{:.0f}"),
        ("Book Value", "book_value_inr", "₹{:.2f}"),
    ]

    for label, key, fmt in fields:
        val = data.get(key, 0.0)
        try:
            formatted = fmt.format(val)
        except (ValueError, TypeError):
            formatted = str(val)
        print(f"  {label:<18} {formatted}")

    print(f"Source: {data.get('source', '?')}")


if __name__ == "__main__":
    print(f"Screener.in MCP smoke-test — {SYMBOL}")

    test_10yr_financials()
    test_peer_comparison()
    test_key_ratios()

    print(f"\n{SEP}")
    print("Screener MCP test COMPLETE ✅")
    print(SEP)
