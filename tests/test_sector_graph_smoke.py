"""Smoke tests for agents/sector_graph.py — no DB, no network, no LLM.

Covers:
- SECTOR_SYMBOLS shape
- _normalize edge cases
- route_to_peers → correct Send objects
- aggregate_results logic (composite score, ranking, sector_signal)
- build_sector_graph compiles without error
- run_sector_analysis raises ValueError for unknown sector
- analyze_single_peer: happy path (mocked yfinance) + error fallback
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

# ── Stub heavy transitive deps before any project imports ────────────────── #
_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

# Only stub packages that are NOT installed in this venv.
# langchain_core and langchain_openai ARE installed — do not stub them or
# langgraph's own imports will break.
for _m in [
    "mcp", "mcp.server", "mcp.server.fastmcp",
    "yfinance",
    "asyncpg", "psycopg", "psycopg_pool",
    "langgraph.checkpoint.postgres",
    "langgraph.checkpoint.postgres.aio",
]:
    sys.modules.setdefault(_m, MagicMock())

# Load sector_graph directly to avoid pulling in agents/__init__ -> llm stack
_sg_file = _ROOT / "agents" / "sector_graph.py"
_spec = importlib.util.spec_from_file_location("agents.sector_graph", _sg_file)
assert _spec and _spec.loader
_sg_mod = importlib.util.module_from_spec(_spec)
sys.modules["agents.sector_graph"] = _sg_mod
_spec.loader.exec_module(_sg_mod)  # type: ignore[union-attr]

from agents.sector_graph import (  # noqa: E402
    SECTOR_SYMBOLS,
    PeerResult,
    SectorAnalysisState,
    _normalize,
    aggregate_results,
    analyze_single_peer,
    build_sector_graph,
    route_to_peers,
    run_sector_analysis,
)


# --------------------------------------------------------------------------- #
# Helpers                                                                       #
# --------------------------------------------------------------------------- #

def _make_peer(symbol: str, **kw: Any) -> PeerResult:
    defaults: dict[str, Any] = dict(
        nse_symbol=symbol, company_name=symbol, sector="IT",
        signal_direction="HOLD", confidence=0.6,
        current_price_inr=1000.0, target_price_inr=1100.0, upside_pct=10.0,
        analysis_summary="", key_positives=[], key_risks=[],
        quarter_verdict="beat", revenue_cr=10000.0, pat_margin_pct=25.0,
        pe_ratio=20.0, roe_pct=30.0, composite_score=0.0, rank=0,
        is_sector_best=False, error="",
    )
    defaults.update(kw)
    return PeerResult(**defaults)  # type: ignore[call-arg]


def _base_state(**kw: Any) -> SectorAnalysisState:
    state: dict[str, Any] = dict(
        sector="IT", symbols=["TCS", "INFY", "WIPRO"],
        session_id="test", peer_results=[],
        sector_ranking=[], sector_winner="",
        sector_signal="neutral", fii_trend="neutral",
        completed=0, total=3,
    )
    state.update(kw)
    return state  # type: ignore[return-value]


# --------------------------------------------------------------------------- #
# SECTOR_SYMBOLS                                                                #
# --------------------------------------------------------------------------- #

class TestSectorSymbols:
    def test_all_sectors_present(self) -> None:
        for s in ("IT", "Banking", "FMCG", "Pharma", "Energy"):
            assert s in SECTOR_SYMBOLS, f"missing sector: {s}"

    def test_each_sector_has_five_symbols(self) -> None:
        for sector, syms in SECTOR_SYMBOLS.items():
            assert len(syms) == 5, f"{sector}: expected 5, got {len(syms)}"

    def test_known_entries(self) -> None:
        assert "TCS" in SECTOR_SYMBOLS["IT"]
        assert "HDFCBANK" in SECTOR_SYMBOLS["Banking"]
        assert "RELIANCE" in SECTOR_SYMBOLS["Energy"]


# --------------------------------------------------------------------------- #
# _normalize                                                                    #
# --------------------------------------------------------------------------- #

class TestNormalize:
    def test_empty(self) -> None:
        assert _normalize([]) == []

    def test_all_same(self) -> None:
        result = _normalize([5.0, 5.0, 5.0])
        assert result == [0.5, 0.5, 0.5]

    def test_range(self) -> None:
        result = _normalize([0.0, 5.0, 10.0])
        assert result[0] == 0.0
        assert result[2] == 1.0
        assert abs(result[1] - 0.5) < 1e-9

    def test_single_element_same(self) -> None:
        assert _normalize([42.0]) == [0.5]

    def test_negative_values(self) -> None:
        result = _normalize([-10.0, 0.0, 10.0])
        assert result[0] == 0.0
        assert result[2] == 1.0


# --------------------------------------------------------------------------- #
# route_to_peers                                                                #
# --------------------------------------------------------------------------- #

class TestRouteToPeers:
    def test_returns_send_per_symbol(self) -> None:
        state = _base_state(symbols=["TCS", "INFY", "WIPRO"])
        sends = route_to_peers(state)
        assert len(sends) == 3

    def test_send_node_name(self) -> None:
        sends = route_to_peers(_base_state())
        for s in sends:
            assert s.node == "analyze_single_peer"

    def test_send_payload_fields(self) -> None:
        state = _base_state(sector="Banking", session_id="sess-123",
                            symbols=["HDFCBANK"])
        send = route_to_peers(state)[0]
        assert send.arg["nse_symbol"] == "HDFCBANK"
        assert send.arg["sector"] == "Banking"
        assert send.arg["session_id"] == "sess-123"

    def test_empty_symbols_returns_no_sends(self) -> None:
        assert route_to_peers(_base_state(symbols=[])) == []


# --------------------------------------------------------------------------- #
# aggregate_results                                                             #
# --------------------------------------------------------------------------- #

class TestAggregateResults:
    def _run(self, coro: Any) -> Any:
        return asyncio.run(coro)

    def test_empty_peers(self) -> None:
        state = _base_state(peer_results=[])
        result = self._run(aggregate_results(state))  # type: ignore[arg-type]
        assert result["sector_ranking"] == []
        assert result["sector_winner"] == ""

    def test_ranking_assigns_rank_1_to_best(self) -> None:
        # TCS: high margin + high ROE → should rank 1
        peers = [
            _make_peer("TCS",  revenue_cr=150000, pat_margin_pct=25.0, roe_pct=45.0, pe_ratio=28.0),
            _make_peer("INFY", revenue_cr=120000, pat_margin_pct=18.0, roe_pct=30.0, pe_ratio=25.0),
            _make_peer("WIPRO",revenue_cr=90000,  pat_margin_pct=12.0, roe_pct=16.0, pe_ratio=22.0),
        ]
        state = _base_state(peer_results=peers)
        result = self._run(aggregate_results(state))  # type: ignore[arg-type]
        ranking = result["sector_ranking"]
        assert ranking[0]["nse_symbol"] == "TCS"
        assert ranking[0]["rank"] == 1
        assert ranking[0]["is_sector_best"] is True
        assert ranking[1]["rank"] == 2
        assert ranking[1]["is_sector_best"] is False

    def test_sector_winner_is_rank_1_symbol(self) -> None:
        peers = [
            _make_peer("TCS",  revenue_cr=150000, pat_margin_pct=25.0, roe_pct=45.0, pe_ratio=28.0),
            _make_peer("INFY", revenue_cr=80000,  pat_margin_pct=18.0, roe_pct=30.0, pe_ratio=25.0),
        ]
        result = self._run(aggregate_results(_base_state(peer_results=peers)))  # type: ignore[arg-type]
        assert result["sector_winner"] == "TCS"

    def test_sector_signal_bullish_threshold(self) -> None:
        # 3/5 = 60% BUY → bullish
        peers = [
            _make_peer(f"S{i}", signal_direction="BUY") for i in range(3)
        ] + [
            _make_peer(f"S{i}", signal_direction="HOLD") for i in range(3, 5)
        ]
        result = self._run(aggregate_results(_base_state(peer_results=peers)))  # type: ignore[arg-type]
        assert result["sector_signal"] == "bullish"

    def test_sector_signal_bearish_threshold(self) -> None:
        # 2/5 = 40% SELL → bearish
        peers = [
            _make_peer(f"S{i}", signal_direction="SELL") for i in range(2)
        ] + [
            _make_peer(f"S{i}", signal_direction="HOLD") for i in range(2, 5)
        ]
        result = self._run(aggregate_results(_base_state(peer_results=peers)))  # type: ignore[arg-type]
        assert result["sector_signal"] == "bearish"

    def test_sector_signal_neutral(self) -> None:
        peers = [_make_peer(f"S{i}", signal_direction="HOLD") for i in range(5)]
        result = self._run(aggregate_results(_base_state(peer_results=peers)))  # type: ignore[arg-type]
        assert result["sector_signal"] == "neutral"

    def test_composite_score_in_zero_one(self) -> None:
        peers = [
            _make_peer("A", revenue_cr=100000, pat_margin_pct=20.0, roe_pct=30.0, pe_ratio=25.0),
            _make_peer("B", revenue_cr=50000,  pat_margin_pct=10.0, roe_pct=15.0, pe_ratio=40.0),
        ]
        result = self._run(aggregate_results(_base_state(peer_results=peers)))  # type: ignore[arg-type]
        for p in result["sector_ranking"]:
            assert 0.0 <= p["composite_score"] <= 1.0, (
                f"{p['nse_symbol']} score={p['composite_score']} out of [0,1]"
            )

    def test_fii_trend_default(self) -> None:
        result = self._run(aggregate_results(_base_state(peer_results=[_make_peer("X")])))  # type: ignore[arg-type]
        assert result["fii_trend"] == "neutral"


# --------------------------------------------------------------------------- #
# analyze_single_peer — mocked happy path & error fallback                    #
# --------------------------------------------------------------------------- #

def _make_no_db_factory() -> MagicMock:
    """Return a mock session factory whose context manager raises immediately.

    analyze_single_peer wraps DB calls in try/except so this lets the
    financials path succeed while the DB path degrades gracefully.
    """
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(side_effect=RuntimeError("no db in test"))
    cm.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=cm)
    return factory


class TestAnalyzeSinglePeer:
    def _run(self, coro: Any) -> Any:
        return asyncio.run(coro)

    def _stub_financials(self) -> dict[str, Any]:
        return {
            "symbol": "TCS", "exchange": "NSE",
            "revenue_cr": 220000.0, "pat_cr": 42000.0,
            "pe_ratio": 28.5, "roe_pct": 45.0,
            "pb_ratio": 12.0, "eps": 110.0,
        }

    def _run_with_stubs(self, state: dict[str, Any],
                        financials: dict[str, Any]) -> dict[str, Any]:
        """Run analyze_single_peer with financials stubbed and DB disabled."""
        # Patch asyncio.to_thread so the sync yfinance call returns our stub.
        # Patch backend.database.get_session_factory at the source so that
        # the lazy import inside analyze_single_peer picks up the mock.
        with patch("agents.sector_graph.asyncio.to_thread",
                   new=AsyncMock(return_value=financials)):
            with patch("backend.database.get_session_factory",
                       return_value=_make_no_db_factory()):
                return self._run(analyze_single_peer(state))

    def test_happy_path_returns_peer_result(self) -> None:
        state = {"nse_symbol": "TCS", "sector": "IT", "session_id": "t1"}
        result = self._run_with_stubs(state, self._stub_financials())

        assert "peer_results" in result
        assert len(result["peer_results"]) == 1
        peer = result["peer_results"][0]
        assert peer["nse_symbol"] == "TCS"
        assert peer["sector"] == "IT"
        assert peer["error"] == ""

    def test_error_fallback_returns_error_peer(self) -> None:
        state = {"nse_symbol": "BADTICKER", "sector": "IT", "session_id": "t2"}

        # Make to_thread raise so the entire try block is skipped
        with patch("agents.sector_graph.asyncio.to_thread",
                   new=AsyncMock(side_effect=Exception("yfinance timeout"))):
            result = self._run(analyze_single_peer(state))

        assert "peer_results" in result
        assert len(result["peer_results"]) == 1
        peer = result["peer_results"][0]
        assert peer["nse_symbol"] == "BADTICKER"
        assert "yfinance timeout" in peer["error"]
        assert peer["composite_score"] == 0.0
        assert peer["rank"] == 0

    def test_pat_margin_computed_correctly(self) -> None:
        state = {"nse_symbol": "TCS", "sector": "IT", "session_id": "t3"}
        fins = {**self._stub_financials(), "revenue_cr": 200.0, "pat_cr": 50.0}
        result = self._run_with_stubs(state, fins)

        peer = result["peer_results"][0]
        assert peer["pat_margin_pct"] == 25.0   # 50/200 * 100

    def test_zero_revenue_gives_zero_margin(self) -> None:
        state = {"nse_symbol": "TCS", "sector": "IT", "session_id": "t4"}
        fins = {**self._stub_financials(), "revenue_cr": 0.0, "pat_cr": 50.0}
        result = self._run_with_stubs(state, fins)

        assert result["peer_results"][0]["pat_margin_pct"] == 0.0


# --------------------------------------------------------------------------- #
# build_sector_graph + run_sector_analysis                                     #
# --------------------------------------------------------------------------- #

class TestBuildSectorGraph:
    def test_graph_compiles(self) -> None:
        graph = build_sector_graph()
        assert graph is not None

    def test_run_raises_for_unknown_sector(self) -> None:
        import pytest
        with pytest.raises(ValueError, match="Unknown sector"):
            asyncio.run(run_sector_analysis("INVALID_SECTOR"))

    def test_run_raises_for_empty_string(self) -> None:
        import pytest
        with pytest.raises(ValueError):
            asyncio.run(run_sector_analysis(""))
