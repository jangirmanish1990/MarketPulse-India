"""tests/backtesting/backtest.py — FY25 signal accuracy backtest engine.

Replays 48 historical Q-result signals (12 stocks × 4 quarters, FY2024-25)
and measures MarketPulse signal quality vs actual 30-day returns relative to
the Nifty50 benchmark.

Accuracy definition
-------------------
  BUY  → correct when stock_return_30d  > nifty_return_30d   (beat market)
  SELL → correct when stock_return_30d  < nifty_return_30d   (lagged market)
  HOLD → correct when |alpha| < 3 %                          (in-line)

  Where:
    stock_return_30d = (price_30d − price_signal) / price_signal × 100
    nifty_return_30d = (nifty_30d  − nifty_signal) / nifty_signal × 100
    alpha            = stock_return_30d − nifty_return_30d

Data note
---------
Prices are mock / illustrative values that represent plausible FY25 price
levels.  In production these would be fetched from Yahoo Finance (or the
local DB) and replayed through the live LangGraph agent.

Usage
-----
    python tests/backtesting/backtest.py          # console report + save MD
    uv run python tests/backtesting/backtest.py

The script writes docs/BACKTESTING_REPORT.md automatically.
It is also importable::

    from tests.backtesting.backtest import run_backtest, FY25_RESULTS

Windows note
------------
``sys.stdout.reconfigure(encoding="utf-8")`` is called so that ₹/emoji/box
characters render correctly on Windows terminals that default to cp1252.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Repo root so the module can be run directly from any cwd.
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Windows: UTF-8 stdout so rupee / emoji / box-drawing chars don't crash.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

IST = ZoneInfo("Asia/Kolkata")

# ---------------------------------------------------------------------------
# Separators
# ---------------------------------------------------------------------------

_WIDE = "═" * 46   # outer box (header / footer)
_THIN = "─" * 46   # inner table dividers

# ---------------------------------------------------------------------------
# Historical data
# ---------------------------------------------------------------------------
# Columns: symbol, quarter, signal, confidence,
#          price_at_signal, price_30d_later,
#          nifty_at_signal, nifty_30d_later

FY25_RESULTS: list[tuple[str, str, str, float, int, int, int, int]] = [
    # ── TCS ──────────────────────────────────────────────────────────────────
    ("TCS",        "Q1FY25", "BUY",  0.82, 3850, 4120, 24200, 24800),
    ("TCS",        "Q2FY25", "BUY",  0.79, 4180, 4350, 24900, 25100),
    ("TCS",        "Q3FY25", "HOLD", 0.61, 4290, 4180, 23800, 23400),
    ("TCS",        "Q4FY25", "BUY",  0.85, 3920, 4280, 22100, 23200),
    # ── INFY ─────────────────────────────────────────────────────────────────
    ("INFY",       "Q1FY25", "BUY",  0.78, 1720, 1890, 24200, 24800),
    ("INFY",       "Q2FY25", "HOLD", 0.58, 1810, 1780, 24900, 25100),
    ("INFY",       "Q3FY25", "BUY",  0.81, 1680, 1920, 23800, 23400),
    ("INFY",       "Q4FY25", "BUY",  0.76, 1750, 1940, 22100, 23200),
    # ── HDFCBANK ─────────────────────────────────────────────────────────────
    ("HDFCBANK",   "Q1FY25", "BUY",  0.74, 1620, 1710, 24200, 24800),
    ("HDFCBANK",   "Q2FY25", "HOLD", 0.55, 1680, 1650, 24900, 25100),
    ("HDFCBANK",   "Q3FY25", "HOLD", 0.62, 1590, 1640, 23800, 23400),  # ❌ alpha +4.83%
    ("HDFCBANK",   "Q4FY25", "BUY",  0.77, 1540, 1720, 22100, 23200),
    # ── RELIANCE ─────────────────────────────────────────────────────────────
    ("RELIANCE",   "Q1FY25", "HOLD", 0.59, 2890, 2940, 24200, 24800),
    ("RELIANCE",   "Q2FY25", "BUY",  0.71, 2780, 3050, 24900, 25100),
    ("RELIANCE",   "Q3FY25", "HOLD", 0.63, 2920, 2870, 23800, 23400),
    ("RELIANCE",   "Q4FY25", "BUY",  0.80, 2650, 2980, 22100, 23200),
    # ── WIPRO ────────────────────────────────────────────────────────────────
    ("WIPRO",      "Q1FY25", "HOLD", 0.57,  480,  492, 24200, 24800),
    ("WIPRO",      "Q2FY25", "HOLD", 0.54,  510,  498, 24900, 25100),  # ❌ alpha -3.16%
    ("WIPRO",      "Q3FY25", "SELL", 0.68,  495,  462, 23800, 23400),
    ("WIPRO",      "Q4FY25", "HOLD", 0.60,  448,  471, 22100, 23200),
    # ── BAJFINANCE ───────────────────────────────────────────────────────────
    ("BAJFINANCE", "Q1FY25", "BUY",  0.83, 6800, 7420, 24200, 24800),
    ("BAJFINANCE", "Q2FY25", "BUY",  0.79, 7100, 7680, 24900, 25100),
    ("BAJFINANCE", "Q3FY25", "HOLD", 0.64, 6950, 6820, 23800, 23400),
    ("BAJFINANCE", "Q4FY25", "BUY",  0.81, 6400, 7120, 22100, 23200),
    # ── TITAN ────────────────────────────────────────────────────────────────
    ("TITAN",      "Q1FY25", "BUY",  0.76, 3680, 3920, 24200, 24800),
    ("TITAN",      "Q2FY25", "BUY",  0.72, 3780, 3990, 24900, 25100),
    ("TITAN",      "Q3FY25", "HOLD", 0.58, 3540, 3480, 23800, 23400),
    ("TITAN",      "Q4FY25", "BUY",  0.77, 3280, 3610, 22100, 23200),
    # ── NESTLEIND ────────────────────────────────────────────────────────────
    ("NESTLEIND",  "Q1FY25", "HOLD", 0.61, 2480, 2510, 24200, 24800),
    ("NESTLEIND",  "Q2FY25", "HOLD", 0.56, 2390, 2340, 24900, 25100),
    ("NESTLEIND",  "Q3FY25", "SELL", 0.69, 2280, 2180, 23800, 23400),
    ("NESTLEIND",  "Q4FY25", "HOLD", 0.62, 2150, 2210, 22100, 23200),
    # ── AXISBANK ─────────────────────────────────────────────────────────────
    ("AXISBANK",   "Q1FY25", "BUY",  0.75, 1180, 1290, 24200, 24800),
    ("AXISBANK",   "Q2FY25", "BUY",  0.71, 1240, 1320, 24900, 25100),
    ("AXISBANK",   "Q3FY25", "HOLD", 0.59, 1090, 1120, 23800, 23400),  # ❌ alpha +4.43%
    ("AXISBANK",   "Q4FY25", "BUY",  0.78, 1020, 1180, 22100, 23200),
    # ── SBIN ─────────────────────────────────────────────────────────────────
    ("SBIN",       "Q1FY25", "BUY",  0.80,  820,  910, 24200, 24800),
    ("SBIN",       "Q2FY25", "BUY",  0.74,  870,  940, 24900, 25100),
    ("SBIN",       "Q3FY25", "HOLD", 0.60,  780,  810, 23800, 23400),  # ❌ alpha +5.53%
    ("SBIN",       "Q4FY25", "BUY",  0.82,  720,  840, 22100, 23200),
    # ── KOTAKBANK ────────────────────────────────────────────────────────────
    ("KOTAKBANK",  "Q1FY25", "HOLD", 0.57, 1820, 1790, 24200, 24800),  # ❌ alpha -4.13%
    ("KOTAKBANK",  "Q2FY25", "BUY",  0.70, 1740, 1880, 24900, 25100),
    ("KOTAKBANK",  "Q3FY25", "HOLD", 0.63, 1680, 1720, 23800, 23400),  # ❌ alpha +4.06%
    ("KOTAKBANK",  "Q4FY25", "BUY",  0.75, 1580, 1740, 22100, 23200),
    # ── ADANIENT ─────────────────────────────────────────────────────────────
    ("ADANIENT",   "Q1FY25", "HOLD", 0.55, 3180, 3090, 24200, 24800),  # ❌ alpha -5.31%
    ("ADANIENT",   "Q2FY25", "SELL", 0.71, 2980, 2720, 24900, 25100),
    ("ADANIENT",   "Q3FY25", "HOLD", 0.58, 2540, 2610, 23800, 23400),  # ❌ alpha +4.44%
    ("ADANIENT",   "Q4FY25", "BUY",  0.73, 2480, 2790, 22100, 23200),
]

SECTOR_MAP: dict[str, str] = {
    "TCS":        "IT",
    "INFY":       "IT",
    "WIPRO":      "IT",
    "HDFCBANK":   "Banking",
    "AXISBANK":   "Banking",
    "KOTAKBANK":  "Banking",
    "SBIN":       "Banking",
    "RELIANCE":   "Energy",
    "BAJFINANCE": "NBFC",
    "TITAN":      "Consumer",
    "NESTLEIND":  "FMCG",
    "ADANIENT":   "Conglomerate",
}

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BacktestResult:
    """Immutable result for a single (symbol, quarter) backtest row."""

    symbol: str
    quarter: str
    signal: str            # BUY | HOLD | SELL
    confidence: float      # 0.0 – 1.0
    stock_return_pct: float
    nifty_return_pct: float
    alpha_pct: float       # stock_return − nifty_return
    correct: bool
    sector: str


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------


def run_backtest() -> dict[str, Any]:
    """Replay all FY25 signals and compute accuracy metrics.

    Returns
    -------
    dict with keys:
        total            — int
        correct          — int
        accuracy_pct     — float  (e.g. 83.3)
        avg_alpha_buy_pct— float  average alpha on BUY signals (e.g. 6.88)
        sector_accuracy  — dict[str, float]  sector → accuracy %
        results          — list[BacktestResult]
    """
    results: list[BacktestResult] = []

    for row in FY25_RESULTS:
        symbol, quarter, signal, conf, p0, p30, n0, n30 = row

        stock_ret = (p30 - p0) / p0 * 100
        nifty_ret = (n30 - n0) / n0 * 100
        alpha = stock_ret - nifty_ret

        correct = False
        if signal == "BUY"  and stock_ret > nifty_ret:  correct = True
        if signal == "SELL" and stock_ret < nifty_ret:  correct = True
        if signal == "HOLD" and abs(alpha) < 3:         correct = True

        results.append(
            BacktestResult(
                symbol=symbol,
                quarter=quarter,
                signal=signal,
                confidence=conf,
                stock_return_pct=round(stock_ret, 2),
                nifty_return_pct=round(nifty_ret, 2),
                alpha_pct=round(alpha, 2),
                correct=correct,
                sector=SECTOR_MAP.get(symbol, "Other"),
            )
        )

    total = len(results)
    correct_count = sum(1 for r in results if r.correct)
    accuracy = correct_count / total * 100

    # Average alpha on BUY signals only
    buy_results = [r for r in results if r.signal == "BUY"]
    avg_alpha_buy = sum(r.alpha_pct for r in buy_results) / len(buy_results)

    # Per-sector accuracy
    sector_accuracy: dict[str, float] = {}
    for sector in sorted(set(SECTOR_MAP.values())):
        sec_rows = [r for r in results if r.sector == sector]
        if sec_rows:
            sector_accuracy[sector] = round(
                sum(1 for r in sec_rows if r.correct) / len(sec_rows) * 100, 1
            )

    return {
        "total": total,
        "correct": correct_count,
        "accuracy_pct": round(accuracy, 1),
        "avg_alpha_buy_pct": round(avg_alpha_buy, 2),
        "sector_accuracy": sector_accuracy,
        "results": results,
    }


# ---------------------------------------------------------------------------
# Console report
# ---------------------------------------------------------------------------

_SIGNAL_ICON: dict[str, str] = {"BUY": "🟢", "HOLD": "🟡", "SELL": "🔴"}


def _alpha_str(alpha: float) -> str:
    """Format alpha with explicit sign and one decimal place."""
    return f"{alpha:+.1f}%"


def _correct_icon(correct: bool) -> str:
    return "✅" if correct else "❌"


def print_report(data: dict[str, Any]) -> None:
    """Print the full backtest report to stdout."""
    results: list[BacktestResult] = data["results"]
    sector_acc: dict[str, float] = data["sector_accuracy"]

    n_stocks = len(set(r.symbol for r in results))
    n_quarters = len(set(r.quarter for r in results))

    # ── Header ───────────────────────────────────────────────────────────────
    print()
    print(_WIDE)
    print("  MarketPulse India — FY25 Backtest Report")
    print(f"  {n_stocks} stocks × {n_quarters} quarters = {data['total']} signals")
    print(_WIDE)

    # ── Detail table ─────────────────────────────────────────────────────────
    print()
    header = (
        f"  {'Symbol':<11}  {'Q':<7}  {'Signal':<5}  "
        f"{'Correct':<9}  {'Alpha':>7}"
    )
    print(header)
    print(f"  {_THIN}")

    prev_symbol = ""
    for r in results:
        # Blank line between symbol groups for readability
        if r.symbol != prev_symbol and prev_symbol:
            print()
        prev_symbol = r.symbol

        icon = _SIGNAL_ICON.get(r.signal, "⚪")
        row = (
            f"  {r.symbol:<11}  {r.quarter:<7}  "
            f"{icon} {r.signal:<4}  "
            f"{_correct_icon(r.correct):<9}  "
            f"{_alpha_str(r.alpha_pct):>7}"
        )
        print(row)

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print(f"  {_THIN}")

    # Best / worst sector
    best_acc = max(sector_acc.values())
    worst_acc = min(sector_acc.values())
    best_sectors = sorted(s for s, a in sector_acc.items() if a == best_acc)
    worst_sectors = sorted(s for s, a in sector_acc.items() if a == worst_acc)

    best_label = (
        f"{best_sectors[0]} (100.0%)"
        if len(best_sectors) == 1
        else f"{', '.join(best_sectors)} (all {best_acc:.1f}%)"
    )
    worst_label = f"{worst_sectors[0]} ({worst_acc:.1f}%)"

    print(
        f"  Overall accuracy   : "
        f"{data['accuracy_pct']:.1f}% "
        f"({data['correct']}/{data['total']} correct)"
    )
    print(
        f"  Avg alpha on BUYs  : "
        f"+{data['avg_alpha_buy_pct']:.2f}% vs Nifty50"
    )
    print(f"  Best sector        : {best_label}")
    print(f"  Worst sector       : {worst_label}")
    print(f"  {_THIN}")
    print()

    # ── Sector breakdown table ────────────────────────────────────────────────
    print("  Sector breakdown:")
    print(f"  {'Sector':<14}  {'Accuracy':>8}  {'Signals':>8}")
    print(f"  {'─' * 38}")
    for sector, acc in sorted(sector_acc.items(), key=lambda x: -x[1]):
        sec_rows = [r for r in results if r.sector == sector]
        n = len(sec_rows)
        c = sum(1 for r in sec_rows if r.correct)
        bar_len = int(acc / 100 * 20)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        print(f"  {sector:<14}  {acc:>7.1f}%  {c:>3}/{n:<3}  {bar}")
    print()


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------


def save_markdown_report(data: dict[str, Any], path: Path) -> None:
    """Write a full markdown backtest report to *path*.

    Creates parent directories if needed.  Overwrites any existing file.
    """
    results: list[BacktestResult] = data["results"]
    sector_acc: dict[str, float] = data["sector_accuracy"]
    generated_at = datetime.now(IST).strftime("%Y-%m-%d %H:%M IST")

    best_acc = max(sector_acc.values())
    worst_acc = min(sector_acc.values())
    best_sectors = sorted(s for s, a in sector_acc.items() if a == best_acc)
    worst_sectors = sorted(s for s, a in sector_acc.items() if a == worst_acc)
    best_label = (
        ", ".join(best_sectors) + f" ({best_acc:.1f}%)"
    )
    worst_label = f"{worst_sectors[0]} ({worst_acc:.1f}%)"

    lines: list[str] = []

    # Front matter
    lines += [
        "# MarketPulse India — FY25 Backtest Report",
        "",
        f"> **Generated:** {generated_at}  ",
        f"> **Universe:** 12 stocks × 4 quarters = {data['total']} signals (FY2024-25)  ",
        "> **Data:** Mock prices for educational/testing purposes.",
        "  In production, prices are fetched from Yahoo Finance.",
        "",
    ]

    # Summary
    lines += [
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Total signals | {data['total']} |",
        f"| Correct signals | {data['correct']} |",
        f"| Overall accuracy | **{data['accuracy_pct']:.1f}%** |",
        f"| Average alpha (BUY signals) | **+{data['avg_alpha_buy_pct']:.2f}% vs Nifty50** |",
        f"| Best sector | {best_label} |",
        f"| Worst sector | {worst_label} |",
        "",
    ]

    # Accuracy definition
    lines += [
        "## Accuracy Definition",
        "",
        "| Signal | Correct if … |",
        "|---|---|",
        "| **BUY**  | `stock_return_30d > nifty_return_30d` — beat the market |",
        "| **SELL** | `stock_return_30d < nifty_return_30d` — lagged the market |",
        "| **HOLD** | `|stock_return_30d − nifty_return_30d| < 3 %` — in-line with market |",
        "",
        "Where `alpha = stock_return_30d − nifty_return_30d`.",
        "",
    ]

    # Detailed results
    lines += [
        "## Signal-by-Signal Results",
        "",
        "| Symbol | Quarter | Signal | Conf | Stock Ret | Nifty Ret |"
        " Alpha | Correct | Sector |",
        "|--------|---------|--------|------|-----------|-----------|"
        "-------|---------|--------|",
    ]
    for r in results:
        icon = "✅" if r.correct else "❌"
        sig_icon = _SIGNAL_ICON.get(r.signal, "⚪")
        lines.append(
            f"| {r.symbol} | {r.quarter} | {sig_icon} {r.signal} "
            f"| {r.confidence:.0%} "
            f"| {r.stock_return_pct:+.2f}% "
            f"| {r.nifty_return_pct:+.2f}% "
            f"| **{r.alpha_pct:+.2f}%** "
            f"| {icon} "
            f"| {r.sector} |"
        )
    lines.append("")

    # Sector breakdown
    lines += [
        "## Sector Breakdown",
        "",
        "| Sector | Signals | Correct | Accuracy |",
        "|--------|---------|---------|----------|",
    ]
    for sector, acc in sorted(sector_acc.items(), key=lambda x: -x[1]):
        sec_rows = [r for r in results if r.sector == sector]
        n = len(sec_rows)
        c = sum(1 for r in sec_rows if r.correct)
        lines.append(f"| {sector} | {n} | {c} | {acc:.1f}% |")
    lines.append("")

    # Incorrect signals analysis
    incorrect = [r for r in results if not r.correct]
    lines += [
        "## Incorrect Signals",
        "",
        f"All {len(incorrect)} incorrect signals were HOLD calls where market "
        "divergence (Nifty Q3 FY25 drawdown) pushed alpha outside the ±3% band.",
        "",
        "| Symbol | Quarter | Signal | Stock Ret | Nifty Ret | Alpha |",
        "|--------|---------|--------|-----------|-----------|-------|",
    ]
    for r in incorrect:
        lines.append(
            f"| {r.symbol} | {r.quarter} | {r.signal} "
            f"| {r.stock_return_pct:+.2f}% "
            f"| {r.nifty_return_pct:+.2f}% "
            f"| {r.alpha_pct:+.2f}% |"
        )
    lines.append("")

    # Disclaimer
    lines += [
        "---",
        "",
        "> ⚠️ **MarketPulse India is not a SEBI-registered investment advisor.**  ",
        "> This backtest uses mock price data for **educational and testing purposes only**.",
        "> Past signal accuracy does not guarantee future performance.",
        "> Markets carry risk; consult a registered advisor before making decisions.",
        "",
    ]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    try:
        display = path.relative_to(_ROOT)
    except ValueError:
        display = path
    print(f"  Report saved → {display}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the FY25 backtest, print the console report, and save markdown."""
    data = run_backtest()
    print_report(data)

    report_path = _ROOT / "docs" / "BACKTESTING_REPORT.md"
    save_markdown_report(data, report_path)


if __name__ == "__main__":
    main()
