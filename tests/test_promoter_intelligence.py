"""Unit tests for the promoter_intelligence LangGraph node.

Covers:
- calculate_promoter_adjustment (all risk × trend combinations)
- calculate_fii_adjustment (all classification combos + divergence penalty)
- promoter_intelligence async node (mock path, error fallback, confidence update)
- PromoterIntelligence / FIIDIIFlow Pydantic model validation
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

# ── Load agents.nodes.institutional DIRECTLY from its .py file ─────────── #
# This bypasses agents/nodes/__init__.py which would drag in langchain_openai
# and the entire LLM stack.  We only need the one module under test.
#
# langchain_core IS installed — do NOT stub it here.  Stubbing it would put a
# MagicMock in sys.modules before the package has been imported, which breaks
# any later test that loads langgraph (langgraph.graph.message imports
# langchain_core.messages and fails with "not a package" when langchain_core
# is a MagicMock).  Just import it so it lands in sys.modules as a real package
# before any setdefault can clobber it.
import langchain_core  # noqa: F401  — ensures real package is in sys.modules
import langchain_core.runnables  # noqa: F401  — pre-load submodule too

# agents.state IS a real, importable module — let it load normally.
# agents.nodes.__init__ is NOT imported (we use spec_from_file_location below).

_inst_file = _ROOT / "agents" / "nodes" / "institutional.py"
_spec = importlib.util.spec_from_file_location(
    "agents.nodes.institutional", _inst_file
)
assert _spec and _spec.loader
_inst_mod = importlib.util.module_from_spec(_spec)
sys.modules["agents.nodes.institutional"] = _inst_mod
_spec.loader.exec_module(_inst_mod)  # type: ignore[union-attr]

import asyncio as _asyncio  # noqa: E402  — used for patch.object in node tests

from agents.nodes.institutional import (  # noqa: E402
    FIIDIIFlow,
    PromoterIntelligence,
    calculate_fii_adjustment,
    calculate_promoter_adjustment,
    promoter_intelligence,
)


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #

def _base_state(**overrides: Any) -> dict[str, Any]:
    """Minimal IndiaMarketState-shaped dict for testing."""
    base: dict[str, Any] = {
        "nse_symbol": "RELIANCE",
        "confidence": 0.70,
        "node_timings": {},
        "promoter_pct": None,
        "promoter_pledging_pct": None,
        "promoter_pledging_risk": None,
        "promoter_trend": None,
        "fii_net_flow_cr": 0.0,
        "fii_sentiment": "neutral",
        "fii_ownership_trend": None,
    }
    base.update(overrides)
    return base


_MOCK_SHP_RELIANCE: dict[str, Any] = {
    "symbol": "RELIANCE",
    "bse_code": "500325",
    "quarter": "Sep 2024",
    "promoter_pct": 50.33,
    "promoter_pledged_pct": 0.0,
    "fii_pct": 23.45,
    "dii_pct": 14.23,
    "retail_pct": 11.99,
    "source": "mock",
    "pledging_risk": "none",
}

_MOCK_FLOWS_NEUTRAL: dict[str, Any] = {
    "fii_net_cr": -823.45,
    "dii_net_cr": 1245.67,
    "fii_classification": "seller",
    "dii_classification": "buyer",
    "sector": "all",
    "week": "current",
    "source": "mock",
}


# --------------------------------------------------------------------------- #
# calculate_promoter_adjustment                                                 #
# --------------------------------------------------------------------------- #

class TestCalculatePromoterAdjustment:
    def test_no_risk_stable(self) -> None:
        assert calculate_promoter_adjustment("none", "stable") == 0.0

    def test_high_risk_stable(self) -> None:
        assert calculate_promoter_adjustment("high", "stable") == -0.10

    def test_medium_risk_stable(self) -> None:
        assert calculate_promoter_adjustment("medium", "stable") == -0.04

    def test_low_risk_stable(self) -> None:
        assert calculate_promoter_adjustment("low", "stable") == -0.02

    def test_none_risk_increasing(self) -> None:
        assert calculate_promoter_adjustment("none", "increasing") == 0.05

    def test_none_risk_decreasing(self) -> None:
        assert calculate_promoter_adjustment("none", "decreasing") == -0.06

    def test_high_risk_increasing(self) -> None:
        # -0.10 + 0.05 = -0.05
        assert calculate_promoter_adjustment("high", "increasing") == -0.05

    def test_high_risk_decreasing(self) -> None:
        # -0.10 - 0.06 = -0.16  → clamped to -0.15
        assert calculate_promoter_adjustment("high", "decreasing") == -0.15

    def test_clamp_upper(self) -> None:
        # none + increasing = +0.05, max is 0.08
        result = calculate_promoter_adjustment("none", "increasing")
        assert result <= 0.08

    def test_clamp_lower(self) -> None:
        result = calculate_promoter_adjustment("high", "decreasing")
        assert result >= -0.15


# --------------------------------------------------------------------------- #
# calculate_fii_adjustment                                                      #
# --------------------------------------------------------------------------- #

class TestCalculateFiiAdjustment:
    def test_strong_buyer_neutral_dii(self) -> None:
        assert calculate_fii_adjustment("strong_buyer", "neutral") == 0.07

    def test_buyer_neutral_dii(self) -> None:
        assert calculate_fii_adjustment("buyer", "neutral") == 0.04

    def test_neutral_neutral(self) -> None:
        assert calculate_fii_adjustment("neutral", "neutral") == 0.0

    def test_seller_neutral_dii(self) -> None:
        assert calculate_fii_adjustment("seller", "neutral") == -0.04

    def test_strong_seller_neutral_dii(self) -> None:
        assert calculate_fii_adjustment("strong_seller", "neutral") == -0.07

    def test_divergence_fii_buying_dii_selling(self) -> None:
        # buyer (+0.04) + divergence (-0.03) = 0.01
        assert calculate_fii_adjustment("buyer", "seller") == 0.01

    def test_divergence_fii_selling_dii_buying(self) -> None:
        # seller (-0.04) + divergence (-0.03) = -0.07
        assert calculate_fii_adjustment("seller", "buyer") == -0.07

    def test_both_buying_no_divergence(self) -> None:
        # Both buying — no divergence penalty
        assert calculate_fii_adjustment("buyer", "strong_buyer") == 0.04

    def test_both_selling_no_divergence(self) -> None:
        # Both selling — no divergence penalty
        assert calculate_fii_adjustment("seller", "strong_seller") == -0.04

    def test_clamp_positive(self) -> None:
        result = calculate_fii_adjustment("strong_buyer", "strong_buyer")
        assert result <= 0.10

    def test_clamp_negative(self) -> None:
        result = calculate_fii_adjustment("strong_seller", "strong_buyer")
        assert result >= -0.10

    def test_unknown_classification(self) -> None:
        # Unknown classification should default to 0
        assert calculate_fii_adjustment("unknown_class", "neutral") == 0.0


# --------------------------------------------------------------------------- #
# promoter_intelligence node — async tests                                     #
# --------------------------------------------------------------------------- #

def _gather_mock(return_value: Any) -> Any:
    """Return an async callable that replaces asyncio.gather.

    Closes any coroutine arguments so they don't leak (pytest warns on
    unawaited coroutines), then returns the fixed return_value.
    """
    async def _mock(*coros: Any) -> Any:
        for coro in coros:
            if hasattr(coro, "close"):
                coro.close()
        return return_value
    return _mock


def _gather_error(exc: Exception) -> Any:
    """Return an async callable that closes its coro args then raises exc."""
    async def _mock(*coros: Any) -> None:
        for coro in coros:
            if hasattr(coro, "close"):
                coro.close()
        raise exc
    return _mock


class TestPromoterIntelligenceNode:
    """Test the async promoter_intelligence node.

    All tests patch asyncio.gather on the live asyncio module object so the
    patch resolves correctly regardless of how the module was loaded.
    asyncio.run() is used (not get_event_loop()) — safe on Python 3.13 + Windows.
    """

    def _run(self, coro: Any) -> Any:
        return asyncio.run(coro)

    def test_happy_path_updates_state(self) -> None:
        state = _base_state()
        with patch.object(_asyncio, "gather",
                          new=_gather_mock((_MOCK_SHP_RELIANCE, _MOCK_FLOWS_NEUTRAL))):
            result = self._run(promoter_intelligence(state, MagicMock()))  # type: ignore[arg-type]

        assert result["promoter_pct"] == 50.33
        assert result["promoter_pledging_pct"] == 0.0
        assert result["promoter_pledging_risk"] == "none"
        assert result["promoter_trend"] == "stable"
        assert result["fii_net_flow_cr"] == -823.45
        assert result["fii_sentiment"] == "seller"
        assert result["fii_ownership_trend"] == "FII seller | DII buyer"

    def test_confidence_adjusted(self) -> None:
        # none/stable promoter → 0.0; seller FII + buyer DII → -0.04 - 0.03 = -0.07
        # 0.70 - 0.07 = 0.63
        state = _base_state(confidence=0.70)
        with patch.object(_asyncio, "gather",
                          new=_gather_mock((_MOCK_SHP_RELIANCE, _MOCK_FLOWS_NEUTRAL))):
            result = self._run(promoter_intelligence(state, MagicMock()))  # type: ignore[arg-type]

        assert result["confidence"] == 0.63
        assert 0.10 <= result["confidence"] <= 0.95

    def test_node_timing_recorded(self) -> None:
        state = _base_state()
        with patch.object(_asyncio, "gather",
                          new=_gather_mock((_MOCK_SHP_RELIANCE, _MOCK_FLOWS_NEUTRAL))):
            result = self._run(promoter_intelligence(state, MagicMock()))  # type: ignore[arg-type]

        assert "promoter_intelligence" in result["node_timings"]
        assert isinstance(result["node_timings"]["promoter_intelligence"], int)

    def test_graceful_fallback_on_exception(self) -> None:
        state = _base_state(confidence=0.70)
        with patch.object(_asyncio, "gather",
                          new=_gather_error(ConnectionError("BSE unreachable"))):
            result = self._run(promoter_intelligence(state, MagicMock()))  # type: ignore[arg-type]

        # State must be returned unchanged — no crash
        assert result["confidence"] == 0.70
        assert result["promoter_pct"] is None

    def test_confidence_none_not_updated(self) -> None:
        """When confidence is None the node should not write a float back."""
        state = _base_state(confidence=None)
        with patch.object(_asyncio, "gather",
                          new=_gather_mock((_MOCK_SHP_RELIANCE, _MOCK_FLOWS_NEUTRAL))):
            result = self._run(promoter_intelligence(state, MagicMock()))  # type: ignore[arg-type]

        assert result["confidence"] is None

    def test_high_pledging_reduces_confidence(self) -> None:
        shp_high = {**_MOCK_SHP_RELIANCE, "pledging_risk": "high", "promoter_pledged_pct": 25.0}
        state = _base_state(confidence=0.75)
        with patch.object(_asyncio, "gather",
                          new=_gather_mock((shp_high, _MOCK_FLOWS_NEUTRAL))):
            result = self._run(promoter_intelligence(state, MagicMock()))  # type: ignore[arg-type]

        # high pledging (-0.10) + seller/buyer FII divergence (-0.07) = -0.17 → clamped
        assert result["confidence"] < 0.75

    def test_confidence_clamped_at_floor(self) -> None:
        shp_high = {**_MOCK_SHP_RELIANCE, "pledging_risk": "high", "promoter_pledged_pct": 25.0}
        flows_ss = {**_MOCK_FLOWS_NEUTRAL, "fii_classification": "strong_seller",
                    "dii_classification": "neutral"}
        state = _base_state(confidence=0.12)
        with patch.object(_asyncio, "gather",
                          new=_gather_mock((shp_high, flows_ss))):
            result = self._run(promoter_intelligence(state, MagicMock()))  # type: ignore[arg-type]

        assert result["confidence"] >= 0.10  # floor enforced

    def test_confidence_clamped_at_ceiling(self) -> None:
        shp_clean = {**_MOCK_SHP_RELIANCE, "pledging_risk": "none"}
        flows_sb = {**_MOCK_FLOWS_NEUTRAL, "fii_classification": "strong_buyer",
                    "dii_classification": "strong_buyer"}
        state = _base_state(confidence=0.94)
        with patch.object(_asyncio, "gather",
                          new=_gather_mock((shp_clean, flows_sb))):
            result = self._run(promoter_intelligence(state, MagicMock()))  # type: ignore[arg-type]

        assert result["confidence"] <= 0.95  # ceiling enforced


# --------------------------------------------------------------------------- #
# Pydantic model validation                                                     #
# --------------------------------------------------------------------------- #

class TestPydanticModels:
    def test_promoter_intelligence_model(self) -> None:
        m = PromoterIntelligence(
            promoter_pct=50.33,
            promoter_pledged_pct=0.0,
            promoter_trend="stable",
            pledging_risk="none",
            confidence_adjustment=0.0,
            signal="neutral",
        )
        assert m.promoter_pct == 50.33
        assert m.pledging_risk == "none"
        assert m.signal == "neutral"

    def test_fii_dii_flow_model(self) -> None:
        m = FIIDIIFlow(
            fii_net_cr=-823.45,
            dii_net_cr=1245.67,
            fii_classification="seller",
            dii_classification="buyer",
            institutional_divergence=True,
            confidence_adjustment=-0.07,
            signal="negative",
        )
        assert m.institutional_divergence is True
        assert m.signal == "negative"
