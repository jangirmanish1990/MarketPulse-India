"""Quick smoke-test for all three MCP servers.

Run from the project root (with the package installed or PYTHONPATH=.):

    python scripts/test_mcps.py

The script makes REAL network calls -- do not run in CI.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Force UTF-8 on Windows consoles (cp1252 chokes on Rs. symbol etc.)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

# Ensure project root is importable when run directly.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from mcp_servers.yfinance_india.server import (  # noqa: E402
    get_financials,
    get_index_data,
    get_price_history,
    get_usd_inr,
)
from mcp_servers.nse.session import nse_get  # noqa: E402


# --------------------------------------------------------------------------- #
# Test 1: yfinance-india-mcp                                                   #
# --------------------------------------------------------------------------- #


def test_yfinance() -> bool:
    print("\n[yfinance-india-mcp]")
    try:
        print("  get_index_data() …")
        indexes = get_index_data()
        nifty_val = indexes.get("nifty50", {}).get("value", "N/A")
        print(f"    Nifty50 = {nifty_val}")

        print("  get_usd_inr() …")
        fx = get_usd_inr()
        print(f"    USD/INR = {fx.get('rate', 'N/A')}")

        print("  get_price_history('TCS') …")
        hist = get_price_history("TCS")
        last5 = hist.get("closes", [])[-5:]
        print(f"    TCS last 5 closes = {last5}")

        print("  get_financials('INFY') …")
        fin = get_financials("INFY")
        print(f"    INFY revenue = ₹{fin.get('revenue_cr', 'N/A')} Cr, PAT = ₹{fin.get('pat_cr', 'N/A')} Cr")

        return True
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return False


# --------------------------------------------------------------------------- #
# Test 2: NSE session                                                           #
# --------------------------------------------------------------------------- #


def test_nse_session() -> bool:
    print("\n[NSE session]")
    try:
        print("  get_live_quote('TCS') via nse_get …")
        data = nse_get("https://www.nseindia.com/api/quote-equity?symbol=TCS")
        ltp = data.get("priceInfo", {}).get("lastPrice", "N/A")
        print(f"    TCS LTP = {ltp}")
        return True
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return False


# --------------------------------------------------------------------------- #
# Main                                                                          #
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    yf_ok = test_yfinance()
    nse_ok = test_nse_session()

    print("\n─── Summary ───────────────────────────────")
    print(f"yfinance: {'PASSED ✓' if yf_ok else 'FAILED ✗'}")
    print(f"NSE session: {'PASSED ✓' if nse_ok else 'FAILED ✗'}")

    sys.exit(0 if (yf_ok and nse_ok) else 1)
