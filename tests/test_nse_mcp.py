"""Tests for the NSE MCP server tools.

External HTTP is mocked via `unittest.mock.patch`; Redis is stubbed out through
monkeypatching `cache_get`/`cache_set` on the server module so tests are
hermetic and fast.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

import mcp_servers.nse.server as nse_server


# --------------------------------------------------------------------------- #
# Fixtures                                                                      #
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _no_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Disable Redis caching for all tests in this module."""
    monkeypatch.setattr(nse_server, "cache_get", lambda _k: None)
    monkeypatch.setattr(nse_server, "cache_set", lambda _k, _v, _ttl: None)


# --------------------------------------------------------------------------- #
# get_live_quote                                                                 #
# --------------------------------------------------------------------------- #

_LIVE_QUOTE_RESPONSE: dict[str, Any] = {
    "priceInfo": {
        "lastPrice": 3500.0,
        "change": 25.0,
        "pChange": 0.72,
        "totalTradedVolume": 1_234_567,
        "upperCP": "3850.00",
        "lowerCP": "3150.00",
        "weekHighLow": {"max": 4200.0, "min": 3100.0},
    },
    "securityInfo": {"marketCap": 12_345_678.0},  # in ₹ Lakhs
}


def test_get_live_quote_basic() -> None:
    with patch.object(nse_server, "nse_get", return_value=_LIVE_QUOTE_RESPONSE):
        result = nse_server.get_live_quote("TCS")

    assert result["symbol"] == "TCS"
    assert result["ltp"] == 3500.0
    assert result["change"] == 25.0
    assert result["change_pct"] == 0.72
    assert result["volume"] == 1_234_567
    assert result["week52_high"] == 4200.0
    assert result["week52_low"] == 3100.0
    assert result["market_cap_cr"] == pytest.approx(123456.78, rel=0.01)


def test_get_live_quote_symbol_uppercased() -> None:
    with patch.object(nse_server, "nse_get", return_value=_LIVE_QUOTE_RESPONSE):
        result = nse_server.get_live_quote("tcs")

    assert result["symbol"] == "TCS"


def test_get_live_quote_empty_on_error() -> None:
    with patch.object(nse_server, "nse_get", side_effect=Exception("network error")):
        result = nse_server.get_live_quote("TCS")

    assert result == {}


# --------------------------------------------------------------------------- #
# get_announcements                                                             #
# --------------------------------------------------------------------------- #

_ANN_RESPONSE: dict[str, Any] = {
    "announcements": [
        {
            "symbol": "TCS",
            "subject": "Outcome of Board Meeting",
            "desc": "The Board has declared an interim dividend.",
            "exchdisstime": "20-May-2026 14:30:00",
            "filingType": "Board Meeting Outcome",
            "attchmntFile": "https://example.com/file.pdf",
        }
    ]
}


def test_get_announcements_parses_fields() -> None:
    with patch.object(nse_server, "nse_get", return_value=_ANN_RESPONSE):
        results = nse_server.get_announcements("TCS", days=7)

    assert len(results) == 1
    ann = results[0]
    assert ann["symbol"] == "TCS"
    assert ann["subject"] == "Outcome of Board Meeting"
    assert ann["announcement_type"] == "Board Meeting Outcome"
    assert "2026" in ann["exchange_datetime"]


def test_get_announcements_empty_on_error() -> None:
    with patch.object(nse_server, "nse_get", side_effect=Exception("timeout")):
        results = nse_server.get_announcements("TCS")

    assert results == []


def test_get_announcements_no_announcements_key() -> None:
    with patch.object(nse_server, "nse_get", return_value={}):
        results = nse_server.get_announcements("TCS")

    assert results == []


# --------------------------------------------------------------------------- #
# get_quarterly_results                                                         #
# --------------------------------------------------------------------------- #

_QR_RESPONSE: dict[str, Any] = {
    "data": [
        {"reDt": "2026-03-31", "revenues": 63945.0, "pat": 12045.0, "dilEPS": 32.5},
        {"reDt": "2025-12-31", "revenues": 61200.0, "pat": 11800.0, "dilEPS": 31.9},
        {"reDt": "2025-09-30", "revenues": 59800.0, "pat": 11500.0, "dilEPS": 31.0},
        {"reDt": "2025-06-30", "revenues": 58000.0, "pat": 11000.0, "dilEPS": 29.5},
    ]
}


def test_get_quarterly_results_returns_requested_count() -> None:
    with patch.object(nse_server, "nse_get", return_value=_QR_RESPONSE):
        results = nse_server.get_quarterly_results("TCS", quarters=2)

    assert len(results) == 2
    assert results[0]["symbol"] == "TCS"
    assert results[0]["revenue_cr"] == 63945.0
    assert results[0]["pat_cr"] == 12045.0
    assert results[0]["eps"] == 32.5


def test_get_quarterly_results_empty_on_error() -> None:
    with patch.object(nse_server, "nse_get", side_effect=RuntimeError("bad")):
        results = nse_server.get_quarterly_results("TCS")

    assert results == []


# --------------------------------------------------------------------------- #
# get_results_calendar                                                           #
# --------------------------------------------------------------------------- #

_CALENDAR_RESPONSE: list[dict[str, Any]] = [
    {"symbol": "TCS", "company": "Tata Consultancy Services", "date": "15-Oct-2026", "purpose": "Quarterly Results"},
    {"symbol": "INFY", "company": "Infosys", "date": "20-Oct-2026", "purpose": "Quarterly Results"},
    {"symbol": "RELIANCE", "company": "Reliance", "date": "25-Oct-2026", "purpose": "Dividend"},
]


def test_get_results_calendar_filters_by_symbol() -> None:
    with patch.object(nse_server, "nse_get", return_value=_CALENDAR_RESPONSE):
        results = nse_server.get_results_calendar(["TCS", "INFY"])

    syms = {r["symbol"] for r in results}
    assert syms == {"TCS", "INFY"}


def test_get_results_calendar_excludes_non_result_events() -> None:
    with patch.object(nse_server, "nse_get", return_value=_CALENDAR_RESPONSE):
        results = nse_server.get_results_calendar(["RELIANCE"])

    assert results == []


# --------------------------------------------------------------------------- #
# get_shareholding_pattern                                                      #
# --------------------------------------------------------------------------- #

_SHP_RESPONSE: list[dict[str, Any]] = [
    {"category": "Promoter", "holdingPercent": 72.3, "pledgedPercent": 2.1, "quarter": "Sep 2026"},
    {"category": "FII", "holdingPercent": 13.5, "quarter": "Sep 2026"},
    {"category": "DII", "holdingPercent": 8.2, "quarter": "Sep 2026"},
    {"category": "Public/Retail", "holdingPercent": 6.0, "quarter": "Sep 2026"},
]


def test_get_shareholding_pattern_fields() -> None:
    with patch.object(nse_server, "nse_get", return_value=_SHP_RESPONSE):
        result = nse_server.get_shareholding_pattern("TCS")

    assert result["symbol"] == "TCS"
    assert result["promoter_pct"] == 72.3
    assert result["fii_pct"] == 13.5
    assert result["dii_pct"] == 8.2
    assert result["promoter_pledged_pct"] == 2.1


def test_get_shareholding_pattern_empty_on_error() -> None:
    with patch.object(nse_server, "nse_get", side_effect=Exception("error")):
        result = nse_server.get_shareholding_pattern("TCS")

    assert result == {}
