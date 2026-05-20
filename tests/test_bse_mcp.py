"""Tests for the BSE MCP server tools.

HTTP calls to api.bseindia.com are mocked via `unittest.mock.patch` so the
tests are hermetic and require no network access.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import mcp_servers.bse.server as bse_server


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #


def _mock_bse_get(payload: Any) -> MagicMock:
    """Patch `bse_server.bse_get` to return *payload*."""
    m = MagicMock(return_value=payload)
    return m


# --------------------------------------------------------------------------- #
# get_filings                                                                   #
# --------------------------------------------------------------------------- #

_FILINGS_RESPONSE: dict[str, Any] = {
    "Table": [
        {
            "SCRIP_CD": "532540",
            "NEWSSUB": "Outcome of Board Meeting",
            "HEADLINE": "Board approved Q4 results",
            "DT_TM": "20/05/2026 14:30:00",
            "ATTACHMENTNAME": "outcome_board.pdf",
        }
    ]
}


def test_get_filings_parses_fields() -> None:
    with patch.object(bse_server, "bse_get", return_value=_FILINGS_RESPONSE):
        results = bse_server.get_filings("TCS", days=7)

    assert len(results) == 1
    filing = results[0]
    assert filing["nse_symbol"] == "TCS"
    assert filing["scrip_code"] == "532540"
    assert filing["filing_type"] == "Outcome of Board Meeting"
    assert "2026" in filing["submission_date_ist"]


def test_get_filings_unknown_symbol_returns_empty() -> None:
    results = bse_server.get_filings("UNKNOWN_TICKER_XYZ")
    assert results == []


def test_get_filings_empty_on_network_error() -> None:
    with patch.object(bse_server, "bse_get", side_effect=Exception("timeout")):
        results = bse_server.get_filings("TCS")

    assert results == []


def test_get_filings_empty_table_key() -> None:
    with patch.object(bse_server, "bse_get", return_value={"Table": []}):
        results = bse_server.get_filings("INFY")

    assert results == []


# --------------------------------------------------------------------------- #
# get_insider_trades                                                            #
# --------------------------------------------------------------------------- #

_INSIDER_RESPONSE: dict[str, Any] = {
    "Table": [
        {
            "Acquirer_Name": "N R Narayana Murthy",
            "Category": "Promoter",
            "Mode_of_Aquisition": "Buy",
            "No_of_Shares": 10_000,
            "Price": 1500.0,
            "Date_of_Allotment": "15/05/2026",
            "Shareholding_Post_Acq": 12.5,
        }
    ]
}


def test_get_insider_trades_buy_classification() -> None:
    with patch.object(bse_server, "bse_get", return_value=_INSIDER_RESPONSE):
        results = bse_server.get_insider_trades("INFY")

    assert len(results) == 1
    trade = results[0]
    assert trade["trader_name"] == "N R Narayana Murthy"
    assert trade["trade_type"] == "buy"
    assert trade["quantity"] == 10_000
    assert trade["avg_price_inr"] == 1500.0
    assert trade["value_cr"] == pytest.approx(1.5, rel=0.01)  # 10000 * 1500 / 1e7 = ₹1.5 Cr
    assert trade["holding_pct_after"] == 12.5


def test_get_insider_trades_sell_classification() -> None:
    sell_payload: dict[str, Any] = {
        "Table": [{"Acquirer_Name": "X", "Category": "Promoter", "Mode_of_Aquisition": "Sell",
                   "No_of_Shares": 100, "Price": 100.0, "Date_of_Allotment": "01/01/2026",
                   "Shareholding_Post_Acq": 10.0}]
    }
    with patch.object(bse_server, "bse_get", return_value=sell_payload):
        results = bse_server.get_insider_trades("INFY")

    assert results[0]["trade_type"] == "sell"


def test_get_insider_trades_unknown_symbol() -> None:
    results = bse_server.get_insider_trades("UNKNOWN_XYZ")
    assert results == []


def test_get_insider_trades_empty_on_error() -> None:
    with patch.object(bse_server, "bse_get", side_effect=RuntimeError("bad")):
        results = bse_server.get_insider_trades("TCS")

    assert results == []


# --------------------------------------------------------------------------- #
# get_sensex_data                                                               #
# --------------------------------------------------------------------------- #

_SENSEX_RESPONSE: dict[str, Any] = {
    "currValue": 75_000.0,
    "prevClose": 74_500.0,
    "high": 75_200.0,
    "low": 74_800.0,
    "yearHigh": 85_000.0,
    "yearLow": 65_000.0,
}


def test_get_sensex_data_fields() -> None:
    with patch.object(bse_server, "bse_get", return_value=_SENSEX_RESPONSE):
        result = bse_server.get_sensex_data()

    assert result["value"] == 75_000.0
    assert result["change"] == pytest.approx(500.0, rel=0.01)
    assert result["change_pct"] == pytest.approx(0.67, rel=0.01)
    assert result["day_high"] == 75_200.0
    assert result["day_low"] == 74_800.0
    assert result["year_high"] == 85_000.0
    assert result["year_low"] == 65_000.0


def test_get_sensex_list_response() -> None:
    """BSE occasionally wraps the Sensex object in a list."""
    payload = [_SENSEX_RESPONSE]
    with patch.object(bse_server, "bse_get", return_value=payload):
        result = bse_server.get_sensex_data()

    assert result["value"] == 75_000.0


def test_get_sensex_empty_on_error() -> None:
    with patch.object(bse_server, "bse_get", side_effect=Exception("error")):
        result = bse_server.get_sensex_data()

    assert result == {}


# --------------------------------------------------------------------------- #
# NSE→BSE mapping sanity                                                       #
# --------------------------------------------------------------------------- #


def test_nse_to_bse_mapping_has_tcs() -> None:
    assert bse_server.NSE_TO_BSE["TCS"] == "532540"


def test_nse_to_bse_mapping_has_reliance() -> None:
    assert bse_server.NSE_TO_BSE["RELIANCE"] == "500325"


def test_nse_to_bse_mapping_covers_30_stocks() -> None:
    assert len(bse_server.NSE_TO_BSE) == 30
