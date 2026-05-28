"""scripts/test_sector_graph.py — integration smoke test for agents/sector_graph.py.

Usage
-----
    uv run python scripts/test_sector_graph.py

What this tests
---------------
Runs ``run_sector_analysis("IT", "test-001")`` end-to-end:

  1. Calls the compiled LangGraph sector graph (Send API fan-out).
  2. Each of the 5 IT stocks (TCS, INFY, WIPRO, HCLTECH, TECHM) is analyzed in
     parallel via ``analyze_single_peer`` — yfinance fetch + optional DB signal.
  3. ``aggregate_results`` ranks them by composite fundamental score.
  4. Prints a formatted ranking table.
  5. Asserts structure + basic sanity (rank ordering, score bounds, winner set).

All assertions are printed individually; the script exits 1 if any fail.

Windows fix: SelectorEventLoop is forced so asyncio.to_thread works correctly.
"""

from __future__ import annotations

import asyncio
import selectors
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Windows: ensure UTF-8 output so ₹ / emojis don't crash
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from agents.sector_graph import SECTOR_SYMBOLS, run_sector_analysis  # noqa: E402

_SEP = "═" * 52
_THIN = "─" * 52

# Signal emoji legend
_SIG_ICON: dict[str, str] = {
    "BUY":  "🟢",
    "SELL": "🔴",
    "HOLD": "🟡",
    "—":    "⚪",
}


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def _sig_icon(direction: str) -> str:
    return _SIG_ICON.get(direction.upper(), "⚪")


def _sector_badge(signal: str) -> str:
    badges = {"bullish": "📈 BULLISH", "bearish": "📉 BEARISH", "neutral": "➡ NEUTRAL"}
    return badges.get(signal, signal.upper())


def _print_table(peers: list[dict[str, Any]]) -> None:
    """Print a formatted ranking table to stdout."""
    header = f"{'Rank':<6} {'Symbol':<12} {'PE':>6} {'ROE':>8} {'Margin':>8} {'Score':>7} {'Signal'}"
    print(header)
    print(_THIN)
    for peer in peers:
        rank = peer.get("rank", 0)
        trophy = "🏆" if peer.get("is_sector_best") else "  "
        symbol = peer.get("nse_symbol", "?")
        pe = peer.get("pe_ratio", 0.0)
        roe = peer.get("roe_pct", 0.0)
        margin = peer.get("pat_margin_pct", 0.0)
        score = peer.get("composite_score", 0.0)
        direction = peer.get("signal_direction", "—")
        err = peer.get("error", "")

        if err:
            print(f"{trophy}{rank:<4} {symbol:<12}  ⚠ error: {err[:40]}")
        else:
            print(
                f"{trophy}{rank:<4} {symbol:<12}"
                f" {pe:>6.1f}"
                f" {roe:>7.1f}%"
                f" {margin:>7.1f}%"
                f" {score:>7.3f}"
                f"  {_sig_icon(direction)} {direction}"
            )


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------


def _assert(cond: bool, msg: str, errors: list[str]) -> None:
    """Record failed assertions without stopping execution."""
    if not cond:
        errors.append(msg)
        print(f"  ✗ FAIL  {msg}")
    else:
        print(f"  ✓ OK    {msg}")


# ---------------------------------------------------------------------------
# Main test runner
# ---------------------------------------------------------------------------


async def _run_test() -> bool:
    """Run the sector graph for IT and validate the result.  Returns True on pass."""
    errors: list[str] = []
    sector = "IT"
    session_id = "test-001"

    print()
    print(_SEP)
    print(f"  Sector Analysis — {sector} ({len(SECTOR_SYMBOLS[sector])} stocks)")
    print(f"  Session: {session_id}")
    print(_SEP)
    print("  Running sector graph (parallel fan-out, please wait)…")
    print()

    # ── 1. Run ───────────────────────────────────────────────────────────── #
    result: dict[str, Any] = await run_sector_analysis(sector, session_id)

    # ── 2. Extract fields ─────────────────────────────────────────────────── #
    sector_signal: str = result.get("sector_signal", "")
    sector_winner: str = result.get("sector_winner", "")
    fii_trend: str = result.get("fii_trend", "")
    peers: list[dict[str, Any]] = result.get("sector_ranking", [])

    # ── 3. Print table ────────────────────────────────────────────────────── #
    _print_table(peers)
    print(_THIN)
    print(f"  Sector winner  : {sector_winner}")
    print(f"  Sector signal  : {_sector_badge(sector_signal)}")
    print(f"  FII trend      : {fii_trend}")
    print(f"  Total analyzed : {len(peers)}/{len(SECTOR_SYMBOLS[sector])}")
    print()

    # ── 4. Assertions ─────────────────────────────────────────────────────── #
    expected_symbols = set(SECTOR_SYMBOLS["IT"])

    # 4a. All 5 IT symbols present in result
    returned_symbols = {p["nse_symbol"] for p in peers}
    _assert(
        returned_symbols == expected_symbols,
        f"All 5 IT symbols returned  (got {returned_symbols})",
        errors,
    )

    # 4b. Ranks are 1–5 with no gaps
    ranks = sorted(p["rank"] for p in peers)
    _assert(
        ranks == list(range(1, len(peers) + 1)),
        f"Ranks are sequential 1–{len(peers)}  (got {ranks})",
        errors,
    )

    # 4c. Exactly one is_sector_best
    best_count = sum(1 for p in peers if p.get("is_sector_best"))
    _assert(best_count == 1, f"Exactly 1 is_sector_best  (got {best_count})", errors)

    # 4d. sector_winner matches rank-1 symbol
    rank1 = next((p["nse_symbol"] for p in peers if p["rank"] == 1), "")
    _assert(
        sector_winner == rank1,
        f"sector_winner == rank-1 symbol  ({sector_winner!r} == {rank1!r})",
        errors,
    )

    # 4e. All composite scores in [0, 1]
    out_of_range = [
        p["nse_symbol"]
        for p in peers
        if not (0.0 <= p.get("composite_score", -1) <= 1.0)
    ]
    _assert(
        not out_of_range,
        f"All composite scores in [0.0, 1.0]  (out-of-range: {out_of_range})",
        errors,
    )

    # 4f. Peers are sorted descending by composite_score
    scores = [p["composite_score"] for p in peers]
    _assert(
        scores == sorted(scores, reverse=True),
        f"Peers sorted descending by composite_score",
        errors,
    )

    # 4g. sector_signal is one of the three valid values
    _assert(
        sector_signal in ("bullish", "neutral", "bearish"),
        f"sector_signal is valid  (got {sector_signal!r})",
        errors,
    )

    # 4h. fii_trend is written
    _assert(
        fii_trend != "",
        f"fii_trend is set  (got {fii_trend!r})",
        errors,
    )

    # 4i. sector_ranking list returned (not empty, same as peers)
    _assert(
        len(result.get("sector_ranking", [])) == len(SECTOR_SYMBOLS["IT"]),
        f"sector_ranking has {len(SECTOR_SYMBOLS['IT'])} entries",
        errors,
    )

    # ── 5. Report ─────────────────────────────────────────────────────────── #
    print()
    print(_SEP)
    if errors:
        for err in errors:
            print(f"  ✗ {err}")
        print(f"  Sector graph test FAILED ❌  ({len(errors)} assertion(s))")
        print(_SEP)
        return False
    else:
        print(f"  Sector graph test PASSED ✅")
        print(_SEP)
        return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the sector graph smoke test.

    Forces SelectorEventLoop on Windows — required for ``asyncio.to_thread``
    to work correctly when the inner threads use selectors (e.g. yfinance's
    HTTP stack on Windows 10/11).
    """
    if sys.platform == "win32":
        loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
        ok = loop.run_until_complete(_run_test())
        loop.close()
    else:
        ok = asyncio.run(_run_test())

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
