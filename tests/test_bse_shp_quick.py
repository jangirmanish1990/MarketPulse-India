"""Quick smoke tests for the new get_shareholding_pattern and get_fii_dii_flows tools.

These tests import the helper functions directly and exercise the mock-data
path without needing a live BSE connection or MCP runtime.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

# ── inject a stub FastMCP so the module loads without mcp installed ──────── #
_stub_mcp_module = MagicMock()
_stub_fastmcp = MagicMock()
_stub_fastmcp.tool = lambda **_kw: (lambda f: f)
_stub_mcp_module.server.fastmcp.FastMCP = lambda name: _stub_fastmcp
sys.modules.setdefault("mcp", _stub_mcp_module)
sys.modules.setdefault("mcp.server", _stub_mcp_module.server)
sys.modules.setdefault("mcp.server.fastmcp", _stub_mcp_module.server.fastmcp)

# Also stub requests so no real network call is made during import
import unittest.mock as _um  # noqa: E402
sys.modules.setdefault("requests", _um.MagicMock())

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

# Now import the server helpers directly
from mcp_servers.bse.server import (  # noqa: E402
    DEFAULT_SHP,
    MOCK_SHP_DATA,
    NSE_TO_BSE,
    _flow_classification,
    _parse_shp_response,
    _pledging_risk,
    get_fii_dii_flows,
    get_shareholding_pattern,
)


# --------------------------------------------------------------------------- #
# _pledging_risk                                                                #
# --------------------------------------------------------------------------- #

class TestPledgingRisk:
    def test_none(self) -> None:
        assert _pledging_risk(0.0) == "none"

    def test_low(self) -> None:
        assert _pledging_risk(0.01) == "low"
        assert _pledging_risk(9.99) == "low"

    def test_medium(self) -> None:
        assert _pledging_risk(10.01) == "medium"
        assert _pledging_risk(20.0) == "medium"

    def test_high(self) -> None:
        assert _pledging_risk(20.01) == "high"
        assert _pledging_risk(99.9) == "high"


# --------------------------------------------------------------------------- #
# _flow_classification                                                          #
# --------------------------------------------------------------------------- #

class TestFlowClassification:
    def test_strong_buyer(self) -> None:
        assert _flow_classification(3000.01) == "strong_buyer"
        assert _flow_classification(9999.0) == "strong_buyer"

    def test_buyer(self) -> None:
        assert _flow_classification(500.01) == "buyer"
        assert _flow_classification(1245.67) == "buyer"

    def test_neutral_zero(self) -> None:
        assert _flow_classification(0.0) == "neutral"

    def test_neutral_edges(self) -> None:
        assert _flow_classification(500.0) == "neutral"
        assert _flow_classification(-500.0) == "neutral"

    def test_seller(self) -> None:
        assert _flow_classification(-500.01) == "seller"
        assert _flow_classification(-823.45) == "seller"

    def test_strong_seller(self) -> None:
        assert _flow_classification(-3000.01) == "strong_seller"


# --------------------------------------------------------------------------- #
# _parse_shp_response                                                           #
# --------------------------------------------------------------------------- #

class TestParseShpResponse:
    def test_returns_none_on_empty(self) -> None:
        assert _parse_shp_response(None) is None
        assert _parse_shp_response({}) is None
        assert _parse_shp_response([]) is None

    def test_returns_none_when_total_below_threshold(self) -> None:
        rows = [{"categoryName": "Promoter & Promoter Group", "percentHolding": "0.5"}]
        assert _parse_shp_response({"Table": rows}) is None

    def test_parses_table_envelope(self) -> None:
        rows: list[dict[str, Any]] = [
            {
                "categoryName": "Promoter & Promoter Group",
                "percentHolding": "55.0",
                "PledgeSharePct": "3.0",
                "Quarter": "Dec 2024",
            },
            {"categoryName": "FII / FPI", "percentHolding": "20.0"},
            {"categoryName": "DII - Mutual Funds", "percentHolding": "12.0"},
            {"categoryName": "Public Retail", "percentHolding": "13.0"},
        ]
        result = _parse_shp_response({"Table": rows})
        assert result is not None
        assert result["promoter_pct"] == 55.0
        assert result["promoter_pledged_pct"] == 3.0
        assert result["fii_pct"] == 20.0
        assert result["dii_pct"] == 12.0
        assert result["retail_pct"] == 13.0
        assert result["quarter"] == "Dec 2024"

    def test_parses_flat_list(self) -> None:
        rows: list[dict[str, Any]] = [
            {"categoryName": "Promoter Group", "percentHolding": "60.0"},
            {"categoryName": "Foreign Portfolio Investors (FPI)", "percentHolding": "15.0"},
            {"categoryName": "public", "percentHolding": "25.0"},
        ]
        result = _parse_shp_response(rows)
        assert result is not None
        assert result["promoter_pct"] == 60.0


# --------------------------------------------------------------------------- #
# get_shareholding_pattern — mock path                                          #
# --------------------------------------------------------------------------- #

class TestGetShareholdingPattern:
    def _call(self, symbol: str) -> dict[str, Any]:
        # Patch bse_get to raise so we always hit the mock path
        with patch("mcp_servers.bse.server.bse_get", side_effect=ConnectionError("offline")):
            return get_shareholding_pattern(symbol)  # type: ignore[return-value]

    def test_reliance_mock_data(self) -> None:
        r = self._call("RELIANCE")
        assert r["symbol"] == "RELIANCE"
        assert r["bse_code"] == NSE_TO_BSE["RELIANCE"]
        assert r["promoter_pct"] == 50.33
        assert r["fii_pct"] == 23.45
        assert r["dii_pct"] == 14.23
        assert r["retail_pct"] == 11.99
        assert r["source"] == "mock"
        assert r["pledging_risk"] == "none"

    def test_tcs_mock_data(self) -> None:
        r = self._call("TCS")
        assert r["promoter_pct"] == 72.19
        assert r["pledging_risk"] == "none"

    def test_adanient_medium_pledging_risk(self) -> None:
        r = self._call("ADANIENT")
        assert r["promoter_pledged_pct"] == 15.43
        assert r["pledging_risk"] == "medium"

    def test_unknown_symbol_uses_default(self) -> None:
        r = self._call("ZZZZZ")
        assert r["symbol"] == "ZZZZZ"
        assert r["bse_code"] == "unknown"
        assert r["promoter_pct"] == DEFAULT_SHP["promoter_pct"]
        assert r["source"] == "mock"

    def test_lowercase_symbol_normalized(self) -> None:
        r = self._call("infy")
        assert r["symbol"] == "INFY"
        assert r["promoter_pct"] == MOCK_SHP_DATA["INFY"]["promoter_pct"]

    def test_hdfcbank_zero_promoter(self) -> None:
        r = self._call("HDFCBANK")
        assert r["promoter_pct"] == 0.0
        assert r["pledging_risk"] == "none"

    def test_return_keys_complete(self) -> None:
        r = self._call("WIPRO")
        expected_keys = {
            "symbol", "bse_code", "quarter", "promoter_pct",
            "promoter_pledged_pct", "fii_pct", "dii_pct", "retail_pct",
            "source", "pledging_risk",
        }
        assert set(r.keys()) == expected_keys


# --------------------------------------------------------------------------- #
# get_fii_dii_flows                                                             #
# --------------------------------------------------------------------------- #

class TestGetFiiDiiFlows:
    def test_default_sector_all(self) -> None:
        r = get_fii_dii_flows()  # type: ignore[call-arg]
        assert r["sector"] == "all"
        assert r["fii_net_cr"] == -823.45
        assert r["dii_net_cr"] == 1245.67
        assert r["fii_classification"] == "seller"
        assert r["dii_classification"] == "buyer"
        assert r["week"] == "current"
        assert r["source"] == "mock"
        assert "note" in r

    def test_sector_echoed(self) -> None:
        r = get_fii_dii_flows(sector="IT")  # type: ignore[call-arg]
        assert r["sector"] == "IT"

    def test_return_keys_complete(self) -> None:
        r = get_fii_dii_flows()  # type: ignore[call-arg]
        expected_keys = {
            "fii_net_cr", "dii_net_cr", "fii_classification",
            "dii_classification", "sector", "week", "source", "note",
        }
        assert set(r.keys()) == expected_keys
