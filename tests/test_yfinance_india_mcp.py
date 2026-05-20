"""Tests for the yfinance India MCP server tools.

yfinance.Ticker and yf.download calls are mocked so tests run offline and fast.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import mcp_servers.yfinance_india.server as yf_server


# --------------------------------------------------------------------------- #
# Fixtures                                                                      #
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _no_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(yf_server, "cache_get", lambda _k: None)
    monkeypatch.setattr(yf_server, "cache_set", lambda _k, _v, _ttl: None)


def _make_ticker_mock(
    info: dict[str, Any] | None = None,
    history_df: pd.DataFrame | None = None,
) -> MagicMock:
    m = MagicMock()
    m.info = info or {}
    if history_df is not None:
        m.history.return_value = history_df
    else:
        m.history.return_value = pd.DataFrame()
    return m


def _sample_history(n: int = 252) -> pd.DataFrame:
    idx = pd.date_range("2025-05-20", periods=n, freq="B")
    closes = [100.0 + i * 0.5 for i in range(n)]
    volumes = [1_000_000] * n
    return pd.DataFrame({"Close": closes, "Volume": volumes}, index=idx)


# --------------------------------------------------------------------------- #
# get_price_history                                                             #
# --------------------------------------------------------------------------- #


def test_get_price_history_structure() -> None:
    hist = _sample_history(10)
    mock_ticker = _make_ticker_mock(history_df=hist)

    with patch.object(yf_server.yf, "Ticker", return_value=mock_ticker):
        result = yf_server.get_price_history("TCS")

    assert result["symbol"] == "TCS"
    assert result["exchange"] == "NSE"
    assert len(result["closes"]) == 10
    assert len(result["dates"]) == 10
    assert len(result["volumes"]) == 10


def test_get_price_history_appends_ns_suffix() -> None:
    hist = _sample_history(5)
    mock_ticker = _make_ticker_mock(history_df=hist)

    with patch.object(yf_server.yf, "Ticker", return_value=mock_ticker) as mock_cls:
        yf_server.get_price_history("TCS", exchange="NSE")

    mock_cls.assert_called_once_with("TCS.NS")


def test_get_price_history_bse_appends_bo_suffix() -> None:
    hist = _sample_history(5)
    mock_ticker = _make_ticker_mock(history_df=hist)

    with patch.object(yf_server.yf, "Ticker", return_value=mock_ticker) as mock_cls:
        yf_server.get_price_history("TCS", exchange="BSE")

    mock_cls.assert_called_once_with("TCS.BO")


def test_get_price_history_empty_on_no_data() -> None:
    mock_ticker = _make_ticker_mock(history_df=pd.DataFrame())

    with patch.object(yf_server.yf, "Ticker", return_value=mock_ticker):
        result = yf_server.get_price_history("TCS")

    assert "error" in result or result == {}


def test_get_price_history_empty_on_exception() -> None:
    with patch.object(yf_server.yf, "Ticker", side_effect=Exception("network")):
        result = yf_server.get_price_history("TCS")

    assert result == {}


def test_get_price_history_returns_pct() -> None:
    hist = _sample_history(260)
    mock_ticker = _make_ticker_mock(history_df=hist)

    with patch.object(yf_server.yf, "Ticker", return_value=mock_ticker):
        result = yf_server.get_price_history("TCS")

    # 1-day return should be non-zero (price increases by 0.5 per day)
    assert "returns_1d_pct" in result
    assert "returns_1y_pct" in result


# --------------------------------------------------------------------------- #
# get_financials                                                                #
# --------------------------------------------------------------------------- #

_FIN_INFO: dict[str, Any] = {
    "totalRevenue": 2_394_500_000_000,  # ~₹2.3 lakh crore
    "netIncomeToCommon": 460_000_000_000,
    "trailingEps": 124.5,
    "trailingPE": 28.2,
    "priceToBook": 13.5,
    "returnOnEquity": 0.425,
    "returnOnAssets": 0.21,
    "debtToEquity": 0.0,
    "marketCap": 13_000_000_000_000,
    "dividendYield": 0.016,
}


def test_get_financials_cr_conversion() -> None:
    mock_ticker = _make_ticker_mock(info=_FIN_INFO)

    with patch.object(yf_server.yf, "Ticker", return_value=mock_ticker):
        result = yf_server.get_financials("TCS")

    assert result["symbol"] == "TCS"
    assert result["revenue_cr"] == pytest.approx(239450.0, rel=0.01)
    assert result["pat_cr"] == pytest.approx(46000.0, rel=0.01)
    assert result["eps"] == 124.5
    assert result["pe_ratio"] == 28.2
    assert result["roe_pct"] == pytest.approx(42.5, rel=0.01)
    assert result["dividend_yield_pct"] == pytest.approx(1.6, rel=0.01)


def test_get_financials_empty_on_error() -> None:
    with patch.object(yf_server.yf, "Ticker", side_effect=Exception("err")):
        result = yf_server.get_financials("TCS")

    assert result == {}


# --------------------------------------------------------------------------- #
# get_index_data                                                                #
# --------------------------------------------------------------------------- #

_INDEX_INFO: dict[str, Any] = {
    "regularMarketPrice": 22_500.0,
    "previousClose": 22_300.0,
    "dayHigh": 22_600.0,
    "dayLow": 22_200.0,
}


def test_get_index_data_contains_all_indices() -> None:
    mock_ticker = _make_ticker_mock(info=_INDEX_INFO)

    with patch.object(yf_server.yf, "Ticker", return_value=mock_ticker):
        result = yf_server.get_index_data()

    for key in ("nifty50", "sensex", "nifty_bank", "nifty_it"):
        assert key in result
        assert "value" in result[key]
        assert "change_pct" in result[key]


def test_get_index_data_change_pct_calculation() -> None:
    mock_ticker = _make_ticker_mock(info=_INDEX_INFO)

    with patch.object(yf_server.yf, "Ticker", return_value=mock_ticker):
        result = yf_server.get_index_data()

    nifty = result["nifty50"]
    expected_pct = round((22_500.0 - 22_300.0) / 22_300.0 * 100, 2)
    assert nifty["change_pct"] == pytest.approx(expected_pct, rel=0.01)


# --------------------------------------------------------------------------- #
# get_usd_inr                                                                   #
# --------------------------------------------------------------------------- #

_USDINR_INFO: dict[str, Any] = {
    "regularMarketPrice": 83.45,
    "previousClose": 83.20,
    "dayHigh": 83.60,
    "dayLow": 83.10,
}


def test_get_usd_inr_fields() -> None:
    mock_ticker = _make_ticker_mock(info=_USDINR_INFO)

    with patch.object(yf_server.yf, "Ticker", return_value=mock_ticker):
        result = yf_server.get_usd_inr()

    assert result["rate"] == pytest.approx(83.45, rel=0.001)
    assert result["day_high"] == pytest.approx(83.60, rel=0.001)
    assert result["day_low"] == pytest.approx(83.10, rel=0.001)
    assert "change_pct" in result


def test_get_usd_inr_empty_on_error() -> None:
    with patch.object(yf_server.yf, "Ticker", side_effect=Exception("err")):
        result = yf_server.get_usd_inr()

    assert result == {}


# --------------------------------------------------------------------------- #
# get_52wk_data                                                                 #
# --------------------------------------------------------------------------- #

_WK52_INFO: dict[str, Any] = {
    "fiftyTwoWeekHigh": 4_500.0,
    "fiftyTwoWeekLow": 3_000.0,
    "currentPrice": 3_750.0,
}


def test_get_52wk_data_position_pct() -> None:
    mock_ticker = _make_ticker_mock(info=_WK52_INFO)

    with patch.object(yf_server.yf, "Ticker", return_value=mock_ticker):
        result = yf_server.get_52wk_data("TCS")

    assert result["week52_high"] == 4_500.0
    assert result["week52_low"] == 3_000.0
    assert result["current_price"] == 3_750.0
    # position: (3750 - 3000) / (4500 - 3000) * 100 = 50%
    assert result["position_pct"] == pytest.approx(50.0, rel=0.01)
    # away_from_high: (4500 - 3750) / 4500 * 100 ≈ 16.67%
    assert result["away_from_high_pct"] == pytest.approx(16.67, rel=0.01)


def test_get_52wk_data_at_high() -> None:
    info = {"fiftyTwoWeekHigh": 4_500.0, "fiftyTwoWeekLow": 3_000.0, "currentPrice": 4_500.0}
    mock_ticker = _make_ticker_mock(info=info)

    with patch.object(yf_server.yf, "Ticker", return_value=mock_ticker):
        result = yf_server.get_52wk_data("TCS")

    assert result["position_pct"] == pytest.approx(100.0, rel=0.01)
    assert result["away_from_high_pct"] == pytest.approx(0.0, abs=0.01)


def test_get_52wk_data_empty_on_error() -> None:
    with patch.object(yf_server.yf, "Ticker", side_effect=Exception("err")):
        result = yf_server.get_52wk_data("TCS")

    assert result == {}


# --------------------------------------------------------------------------- #
# _ticker helper                                                                #
# --------------------------------------------------------------------------- #


def test_ticker_nse_suffix() -> None:
    assert yf_server._ticker("RELIANCE", "NSE") == "RELIANCE.NS"


def test_ticker_bse_suffix() -> None:
    assert yf_server._ticker("RELIANCE", "BSE") == "RELIANCE.BO"


def test_ticker_defaults_to_ns() -> None:
    assert yf_server._ticker("INFY") == "INFY.NS"
