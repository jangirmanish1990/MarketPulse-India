"""pytest unit tests for the FY25 backtest engine.

These tests are intentionally fast (pure-Python, no I/O) and validate:
  - BacktestResult construction and immutability
  - Individual alpha / correctness calculations (spot-checks)
  - Overall accuracy / BUY-alpha aggregate stats
  - Sector breakdown structure and known values
  - Markdown report generation (path creation, content checks)

All assertions are deterministic — the expected values were computed
analytically from the mock dataset in FY25_RESULTS.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from tests.backtesting.backtest import (
    FY25_RESULTS,
    SECTOR_MAP,
    BacktestResult,
    run_backtest,
    save_markdown_report,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def backtest_data() -> dict:
    """Run the backtest once for the whole test module."""
    return run_backtest()


@pytest.fixture(scope="module")
def results(backtest_data: dict) -> list[BacktestResult]:
    return backtest_data["results"]


# ---------------------------------------------------------------------------
# FY25_RESULTS data integrity
# ---------------------------------------------------------------------------


def test_fy25_results_count() -> None:
    assert len(FY25_RESULTS) == 48, "Expected 12 stocks × 4 quarters"


def test_fy25_results_tuple_shape() -> None:
    for row in FY25_RESULTS:
        assert len(row) == 8, f"Expected 8-tuple, got {len(row)}: {row}"


def test_fy25_results_signals_valid() -> None:
    valid = {"BUY", "HOLD", "SELL"}
    for sym, q, sig, *_ in FY25_RESULTS:
        assert sig in valid, f"{sym} {q}: invalid signal '{sig}'"


def test_fy25_results_confidence_range() -> None:
    for sym, q, sig, conf, *_ in FY25_RESULTS:
        assert 0.0 <= conf <= 1.0, f"{sym} {q}: confidence {conf} out of range"


def test_fy25_results_prices_positive() -> None:
    for sym, q, sig, conf, p0, p30, n0, n30 in FY25_RESULTS:
        assert p0 > 0 and p30 > 0, f"{sym} {q}: non-positive price"
        assert n0 > 0 and n30 > 0, f"{sym} {q}: non-positive Nifty level"


def test_sector_map_covers_all_symbols() -> None:
    symbols_in_data = {row[0] for row in FY25_RESULTS}
    assert symbols_in_data == set(SECTOR_MAP.keys())


# ---------------------------------------------------------------------------
# BacktestResult dataclass
# ---------------------------------------------------------------------------


def test_backtest_result_frozen() -> None:
    r = BacktestResult(
        symbol="TCS", quarter="Q1FY25", signal="BUY", confidence=0.82,
        stock_return_pct=7.01, nifty_return_pct=2.48, alpha_pct=4.53,
        correct=True, sector="IT",
    )
    with pytest.raises(Exception):
        r.symbol = "INFY"  # type: ignore[misc]


def test_backtest_result_fields() -> None:
    r = BacktestResult(
        symbol="WIPRO", quarter="Q3FY25", signal="SELL", confidence=0.68,
        stock_return_pct=-6.67, nifty_return_pct=-1.68, alpha_pct=-4.99,
        correct=True, sector="IT",
    )
    assert r.signal == "SELL"
    assert r.correct is True
    assert r.alpha_pct == pytest.approx(-4.99)


# ---------------------------------------------------------------------------
# Correctness logic — spot checks on known rows
# ---------------------------------------------------------------------------


def _find(results: list[BacktestResult], sym: str, q: str) -> BacktestResult:
    for r in results:
        if r.symbol == sym and r.quarter == q:
            return r
    raise KeyError(f"Not found: {sym} {q}")


def test_tcs_q1_buy_correct(results: list[BacktestResult]) -> None:
    r = _find(results, "TCS", "Q1FY25")
    assert r.signal == "BUY"
    assert r.correct is True
    assert r.alpha_pct == pytest.approx(4.53, abs=0.01)


def test_hdfcbank_q3_hold_incorrect(results: list[BacktestResult]) -> None:
    """HOLD incorrect: alpha=+4.83% exceeds the ±3% band."""
    r = _find(results, "HDFCBANK", "Q3FY25")
    assert r.signal == "HOLD"
    assert r.correct is False
    assert abs(r.alpha_pct) > 3.0


def test_wipro_q3_sell_correct(results: list[BacktestResult]) -> None:
    r = _find(results, "WIPRO", "Q3FY25")
    assert r.signal == "SELL"
    assert r.correct is True
    assert r.stock_return_pct < r.nifty_return_pct


def test_adanient_q2_sell_correct(results: list[BacktestResult]) -> None:
    r = _find(results, "ADANIENT", "Q2FY25")
    assert r.signal == "SELL"
    assert r.correct is True
    assert r.alpha_pct < -3.0


def test_infy_q3_buy_large_alpha(results: list[BacktestResult]) -> None:
    """INFY Q3: Nifty fell while INFY surged → huge alpha."""
    r = _find(results, "INFY", "Q3FY25")
    assert r.signal == "BUY"
    assert r.correct is True
    assert r.alpha_pct > 15.0


def test_reliance_q3_hold_near_zero_alpha(results: list[BacktestResult]) -> None:
    """RELIANCE Q3: both fell almost identically → alpha ≈ 0."""
    r = _find(results, "RELIANCE", "Q3FY25")
    assert r.signal == "HOLD"
    assert r.correct is True
    assert abs(r.alpha_pct) < 0.1


# ---------------------------------------------------------------------------
# run_backtest() aggregates
# ---------------------------------------------------------------------------


def test_total_signals(backtest_data: dict) -> None:
    assert backtest_data["total"] == 48


def test_correct_count(backtest_data: dict) -> None:
    assert backtest_data["correct"] == 40


def test_accuracy_pct(backtest_data: dict) -> None:
    assert backtest_data["accuracy_pct"] == pytest.approx(83.3, abs=0.1)


def test_avg_alpha_buy(backtest_data: dict) -> None:
    assert backtest_data["avg_alpha_buy_pct"] == pytest.approx(6.88, abs=0.05)


def test_results_list_length(backtest_data: dict) -> None:
    assert len(backtest_data["results"]) == 48


# ---------------------------------------------------------------------------
# Sector accuracy
# ---------------------------------------------------------------------------


def test_sector_accuracy_keys(backtest_data: dict) -> None:
    expected = {"IT", "Banking", "Energy", "NBFC", "Consumer", "FMCG", "Conglomerate"}
    assert set(backtest_data["sector_accuracy"].keys()) == expected


def test_perfect_sectors(backtest_data: dict) -> None:
    for sector in ("Energy", "NBFC", "Consumer", "FMCG"):
        assert backtest_data["sector_accuracy"][sector] == pytest.approx(100.0)


def test_it_sector_accuracy(backtest_data: dict) -> None:
    assert backtest_data["sector_accuracy"]["IT"] == pytest.approx(91.7, abs=0.1)


def test_banking_sector_accuracy(backtest_data: dict) -> None:
    assert backtest_data["sector_accuracy"]["Banking"] == pytest.approx(68.8, abs=0.1)


def test_conglomerate_sector_accuracy(backtest_data: dict) -> None:
    assert backtest_data["sector_accuracy"]["Conglomerate"] == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# Incorrect signal patterns
# ---------------------------------------------------------------------------


def test_all_incorrect_are_hold(backtest_data: dict) -> None:
    """All 8 incorrect signals are HOLDs whose alpha crossed ±3%."""
    incorrect = [r for r in backtest_data["results"] if not r.correct]
    assert len(incorrect) == 8
    for r in incorrect:
        assert r.signal == "HOLD", f"{r.symbol} {r.quarter}: expected HOLD, got {r.signal}"
        assert abs(r.alpha_pct) > 3.0, f"{r.symbol} {r.quarter}: |alpha|={abs(r.alpha_pct)}"


def test_buy_signals_all_correct(backtest_data: dict) -> None:
    """Every BUY signal beat the Nifty50 — no BUY should be wrong."""
    buy_results = [r for r in backtest_data["results"] if r.signal == "BUY"]
    wrong = [r for r in buy_results if not r.correct]
    assert wrong == [], f"BUY signals that were wrong: {[(r.symbol, r.quarter) for r in wrong]}"


def test_sell_signals_all_correct(backtest_data: dict) -> None:
    """Every SELL signal lagged the Nifty50."""
    sell_results = [r for r in backtest_data["results"] if r.signal == "SELL"]
    wrong = [r for r in sell_results if not r.correct]
    assert wrong == [], f"SELL signals that were wrong: {[(r.symbol, r.quarter) for r in wrong]}"


def test_buy_signal_count() -> None:
    assert sum(1 for _, _, sig, *_ in FY25_RESULTS if sig == "BUY") == 25


def test_sell_signal_count() -> None:
    assert sum(1 for _, _, sig, *_ in FY25_RESULTS if sig == "SELL") == 3


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------


def test_save_markdown_creates_file(backtest_data: dict) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "sub" / "REPORT.md"
        save_markdown_report(backtest_data, path)
        assert path.exists()


def test_save_markdown_content(backtest_data: dict) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "REPORT.md"
        save_markdown_report(backtest_data, path)
        content = path.read_text(encoding="utf-8")

        assert "FY25 Backtest Report" in content
        assert "83.3%" in content           # overall accuracy
        assert "6.88%" in content           # avg BUY alpha
        assert "SEBI" in content            # disclaimer present
        assert "| TCS |" in content         # detail table row
        assert "| ADANIENT |" in content    # detail table row
        assert "Conglomerate" in content    # sector table
        assert "## Incorrect Signals" in content


def test_save_markdown_sebi_disclaimer(backtest_data: dict) -> None:
    """The SEBI disclaimer must be present in any signal-bearing report."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "REPORT.md"
        save_markdown_report(backtest_data, path)
        content = path.read_text(encoding="utf-8")
        assert "not a SEBI-registered investment advisor" in content.lower() or \
               "SEBI" in content
