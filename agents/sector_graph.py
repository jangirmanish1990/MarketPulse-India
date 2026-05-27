"""agents/sector_graph.py — parallel sector analysis graph (LangGraph Send API).

This is a **separate** compiled graph from the main analysis pipeline.  It fans
out over every stock in a sector simultaneously using LangGraph's Send API,
collects the results via an `operator.add` reducer, then ranks stocks by a
composite fundamental score.

Topology
--------

    START
      │
      └─[Send × N stocks]─► analyze_single_peer  (parallel fan-out)
                                    │
                               [all done]
                                    │
                            aggregate_results
                                    │
                                   END

Implementation notes
--------------------
• ``route_to_peers`` returns ``list[Send]`` — it is used as the **routing
  function** for ``add_conditional_edges``, not as a node.  LangGraph nodes
  must return state-update dicts; a Send-returning function is incompatible
  with ``add_node``.

• ``peer_results`` is annotated with ``operator.add`` so every parallel branch
  appends its ``[PeerResult]`` without overwriting the others.

• Each ``analyze_single_peer`` call is fully isolated and catches all
  exceptions — a single failing stock never aborts the whole sector run.

• All sync MCP / DB calls are wrapped in ``asyncio.to_thread`` so the async
  event loop is never blocked.
"""

from __future__ import annotations

import asyncio
import logging
import operator
from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Sector → constituent symbols                                                  #
# --------------------------------------------------------------------------- #

SECTOR_SYMBOLS: dict[str, list[str]] = {
    "IT":      ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM"],
    "Banking": ["HDFCBANK", "ICICIBANK", "KOTAKBANK", "AXISBANK", "SBIN"],
    "FMCG":    ["HINDUNILVR", "ITC", "NESTLEIND", "DABUR", "MARICO"],
    "Pharma":  ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "AUROPHARMA"],
    "Energy":  ["RELIANCE", "ONGC", "NTPC", "POWERGRID", "COALINDIA"],
}


# --------------------------------------------------------------------------- #
# State types                                                                   #
# --------------------------------------------------------------------------- #


class PeerResult(TypedDict):
    """Per-stock analysis result.  All fields have safe defaults so failed
    stocks can still be included in the ranking with rank=0 + error set."""

    nse_symbol: str
    company_name: str
    sector: str
    signal_direction: str
    confidence: float
    current_price_inr: float
    target_price_inr: float
    upside_pct: float
    analysis_summary: str
    key_positives: list  # type: ignore[type-arg]
    key_risks: list  # type: ignore[type-arg]
    quarter_verdict: str
    revenue_cr: float
    pat_margin_pct: float
    pe_ratio: float
    roe_pct: float
    composite_score: float
    rank: int
    is_sector_best: bool
    error: str


class SectorAnalysisState(TypedDict):
    """Graph-wide state.

    ``peer_results`` uses ``operator.add`` as its reducer so each parallel
    ``analyze_single_peer`` branch appends its ``[PeerResult]`` into the
    shared list rather than clobbering the previous results.
    """

    sector: str
    symbols: list[str]
    session_id: str
    # Annotated with operator.add → parallel branches merge via list concatenation
    peer_results: Annotated[list[PeerResult], operator.add]
    sector_ranking: list[PeerResult]
    sector_winner: str
    sector_signal: Literal["bullish", "neutral", "bearish"]
    fii_trend: str
    completed: int
    total: int


# --------------------------------------------------------------------------- #
# Routing — Send API fan-out                                                    #
# --------------------------------------------------------------------------- #


def route_to_peers(state: SectorAnalysisState) -> list[Send]:
    """Return one Send per symbol so LangGraph runs them in parallel.

    Each Send dispatches a minimal dict to ``analyze_single_peer``.  The node
    receives only what it needs; the full SectorAnalysisState is not copied.

    Note: this function returns ``list[Send]`` so it **must not** be added via
    ``graph.add_node`` — it is used exclusively as the routing function for
    ``graph.add_conditional_edges``.
    """
    return [
        Send(
            "analyze_single_peer",
            {
                "nse_symbol": symbol,
                "sector": state["sector"],
                "session_id": state["session_id"],
            },
        )
        for symbol in state["symbols"]
    ]


# --------------------------------------------------------------------------- #
# Single-stock analysis node                                                    #
# --------------------------------------------------------------------------- #


def _make_error_peer(symbol: str, sector: str, error: str) -> PeerResult:
    """Return a zero-filled PeerResult for stocks that failed to fetch."""
    return PeerResult(
        nse_symbol=symbol,
        company_name=symbol,
        sector=sector,
        signal_direction="—",
        confidence=0.0,
        current_price_inr=0.0,
        target_price_inr=0.0,
        upside_pct=0.0,
        analysis_summary="",
        key_positives=[],
        key_risks=[],
        quarter_verdict="—",
        revenue_cr=0.0,
        pat_margin_pct=0.0,
        pe_ratio=0.0,
        roe_pct=0.0,
        composite_score=0.0,
        rank=0,
        is_sector_best=False,
        error=error,
    )


async def analyze_single_peer(state: dict[str, Any]) -> dict[str, list[PeerResult]]:
    """Fetch financials + latest DB signal for a single stock.

    Receives a minimal dict ``{nse_symbol, sector, session_id}`` from Send.
    Returns ``{"peer_results": [PeerResult]}`` — the ``operator.add`` reducer
    on the parent graph merges all parallel results into one list.

    Fast path: no RAG, no LLM — only yfinance financials + last stored signal.
    All exceptions are caught; the stock gets an error PeerResult so the sector
    run is never aborted by a single failing ticker.
    """
    symbol: str = state["nse_symbol"]
    sector: str = state["sector"]

    try:
        # ── 1. Financials from yfinance (sync → thread) ───────────────────
        from mcp_servers.yfinance_india.server import get_financials  # noqa: PLC0415

        financials: dict[str, Any] = await asyncio.to_thread(
            get_financials, symbol, "NSE"
        )

        # ── 2. Latest stored signal from DB (best-effort) ─────────────────
        from backend.database import get_session_factory  # noqa: PLC0415
        from backend.repositories import SignalRepo  # noqa: PLC0415

        latest_signal: Any = None
        try:
            factory = get_session_factory()
            async with factory() as db:
                signals = await SignalRepo(db).get_by_symbol(symbol, limit=1)
                if signals:
                    latest_signal = signals[0]
        except Exception as db_exc:
            logger.debug("[sector_graph] DB signal lookup failed for %s: %s", symbol, db_exc)

        # ── 3. Company name from indian_stocks (best-effort) ──────────────
        company_name: str = symbol
        try:
            from backend.models import IndianStock  # noqa: PLC0415
            from sqlalchemy import select  # noqa: PLC0415

            factory2 = get_session_factory()
            async with factory2() as db:
                result = await db.execute(
                    select(IndianStock).where(IndianStock.nse_symbol == symbol)
                )
                stock = result.scalar_one_or_none()
                if stock:
                    company_name = stock.company_name or symbol
        except Exception as name_exc:
            logger.debug("[sector_graph] Company name lookup failed for %s: %s", symbol, name_exc)

        # ── 4. Derive computed metrics ────────────────────────────────────
        pe_ratio: float = float(financials.get("pe_ratio") or 0)
        roe_pct: float = float(financials.get("roe_pct") or 0)
        revenue_cr: float = float(financials.get("revenue_cr") or 0)
        pat_cr: float = float(financials.get("pat_cr") or 0)
        pat_margin: float = round((pat_cr / revenue_cr * 100) if revenue_cr > 0 else 0.0, 1)

        # ── 5. Pull signal fields (default to neutral placeholders) ───────
        sig_direction: str = latest_signal.direction if latest_signal else "—"
        sig_confidence: float = float(latest_signal.confidence) if latest_signal else 0.0
        sig_current: float = float(latest_signal.current_price_inr or 0) if latest_signal else 0.0
        sig_target: float = float(latest_signal.target_price_inr or 0) if latest_signal else 0.0
        sig_upside: float = float(latest_signal.upside_pct or 0) if latest_signal else 0.0

        peer = PeerResult(
            nse_symbol=symbol,
            company_name=company_name,
            sector=sector,
            signal_direction=sig_direction,
            confidence=sig_confidence,
            current_price_inr=sig_current,
            target_price_inr=sig_target,
            upside_pct=sig_upside,
            analysis_summary="",
            key_positives=[],
            key_risks=[],
            quarter_verdict="—",
            revenue_cr=revenue_cr,
            pat_margin_pct=pat_margin,
            pe_ratio=round(pe_ratio, 1),
            roe_pct=round(roe_pct, 1),
            composite_score=0.0,    # filled in by aggregate_results
            rank=0,                 # filled in by aggregate_results
            is_sector_best=False,   # filled in by aggregate_results
            error="",
        )

        logger.info("[sector_graph] %s analyzed: PE=%.1f, ROE=%.1f%%", symbol, pe_ratio, roe_pct)
        print(f"[sector_graph] {symbol} analyzed: PE={pe_ratio:.1f}, ROE={roe_pct:.1f}%")
        return {"peer_results": [peer]}

    except Exception as exc:
        logger.warning("[sector_graph] %s failed: %s", symbol, exc)
        print(f"[sector_graph] {symbol} failed: {exc}")
        return {"peer_results": [_make_error_peer(symbol, sector, str(exc))]}


# --------------------------------------------------------------------------- #
# Normalisation helper                                                          #
# --------------------------------------------------------------------------- #


def _normalize(values: list[float]) -> list[float]:
    """Min-max normalize a list to [0, 1].

    Returns [0.5, …] when all values are identical to avoid division by zero.
    """
    if not values:
        return []
    min_v = min(values)
    max_v = max(values)
    if max_v == min_v:
        return [0.5] * len(values)
    rng = max_v - min_v
    return [(v - min_v) / rng for v in values]


# --------------------------------------------------------------------------- #
# Aggregator node                                                               #
# --------------------------------------------------------------------------- #


async def aggregate_results(
    state: SectorAnalysisState,
) -> dict[str, Any]:
    """Rank peers by composite score and determine the sector signal.

    Composite score (higher = better)
    ----------------------------------
    Revenue scale  25%  (higher = larger / faster-growing business)
    PAT margin     30%  (higher = more profitable)
    ROE            30%  (higher = better capital efficiency)
    PE (inverted)  15%  (lower PE = cheaper; we invert so higher = better)

    All four metrics are min-max normalised before weighting so they are
    comparable across wildly different scales (e.g. TCS vs MARICO).

    Sector signal
    -------------
    ≥ 60% of peers with BUY signal → "bullish"
    ≥ 40% of peers with SELL signal → "bearish"
    otherwise → "neutral"
    """
    peers: list[PeerResult] = list(state["peer_results"])

    if not peers:
        logger.warning("[sector_graph] aggregate_results called with no peers")
        return {
            "peer_results": [],
            "sector_ranking": [],
            "sector_winner": "",
            "sector_signal": "neutral",
            "fii_trend": "neutral",
        }

    # ── 1. Build normalised metric vectors ──────────────────────────────── #
    rev_vals = [p["revenue_cr"] for p in peers]
    margin_vals = [p["pat_margin_pct"] for p in peers]
    roe_vals = [p["roe_pct"] for p in peers]
    # Invert PE: lower PE → higher value → better
    pe_inv_vals = [1.0 / max(p["pe_ratio"], 1.0) for p in peers]

    norm_rev = _normalize(rev_vals)
    norm_margin = _normalize(margin_vals)
    norm_roe = _normalize(roe_vals)
    norm_pe = _normalize(pe_inv_vals)

    # ── 2. Apply weights and store composite_score ───────────────────────── #
    for i, peer in enumerate(peers):
        score = (
            norm_rev[i]    * 0.25
            + norm_margin[i] * 0.30
            + norm_roe[i]    * 0.30
            + norm_pe[i]     * 0.15
        )
        peer["composite_score"] = round(score, 3)

    # ── 3. Sort descending, assign ranks ────────────────────────────────── #
    sorted_peers = sorted(peers, key=lambda p: p["composite_score"], reverse=True)

    for i, peer in enumerate(sorted_peers):
        peer["rank"] = i + 1
        peer["is_sector_best"] = i == 0

    # ── 4. Derive sector signal from stored signal directions ────────────── #
    total = len(sorted_peers)
    buy_count = sum(1 for p in sorted_peers if p["signal_direction"] == "BUY")
    sell_count = sum(1 for p in sorted_peers if p["signal_direction"] == "SELL")

    if buy_count >= total * 0.6:
        sector_signal: Literal["bullish", "neutral", "bearish"] = "bullish"
    elif sell_count >= total * 0.4:
        sector_signal = "bearish"
    else:
        sector_signal = "neutral"

    winner = sorted_peers[0]["nse_symbol"] if sorted_peers else ""

    print(
        f"[sector_graph] Aggregated {len(peers)} peers. "
        f"Winner: {winner} | Signal: {sector_signal}"
    )

    return {
        "peer_results": sorted_peers,
        "sector_ranking": sorted_peers,
        "sector_winner": winner,
        "sector_signal": sector_signal,
        "fii_trend": "neutral",
    }


# --------------------------------------------------------------------------- #
# Graph factory                                                                 #
# --------------------------------------------------------------------------- #


def build_sector_graph() -> Any:
    """Compile and return the sector analysis graph (no checkpointer needed).

    Topology
    --------
    START → [Send × N] → analyze_single_peer (× N, parallel)
                                   ↓
                          aggregate_results → END
    """
    graph: StateGraph = StateGraph(SectorAnalysisState)  # type: ignore[type-arg]

    # ── Nodes ─────────────────────────────────────────────────────────────
    # Note: route_to_peers is NOT added as a node — it returns list[Send],
    # which LangGraph only accepts as a routing function, not a node body.
    graph.add_node("analyze_single_peer", analyze_single_peer)  # type: ignore[arg-type]
    graph.add_node("aggregate_results", aggregate_results)  # type: ignore[arg-type]

    # ── Fan-out from START via Send API ──────────────────────────────────
    graph.add_conditional_edges(
        START,
        route_to_peers,
        ["analyze_single_peer"],   # declare reachable target nodes
    )

    # ── Fan-in: all parallel branches converge here ───────────────────────
    graph.add_edge("analyze_single_peer", "aggregate_results")
    graph.add_edge("aggregate_results", END)

    return graph.compile()


# --------------------------------------------------------------------------- #
# Public API                                                                    #
# --------------------------------------------------------------------------- #


async def run_sector_analysis(
    sector: str,
    session_id: str = "sector-analysis",
) -> dict[str, Any]:
    """Run the sector graph and return the final SectorAnalysisState.

    Parameters
    ----------
    sector:
        One of the keys in SECTOR_SYMBOLS (``"IT"``, ``"Banking"``, …).
    session_id:
        Arbitrary string for tracing / logging; defaults to
        ``"sector-analysis"``.

    Raises
    ------
    ValueError
        If *sector* is not in SECTOR_SYMBOLS.
    """
    symbols = SECTOR_SYMBOLS.get(sector)
    if not symbols:
        raise ValueError(
            f"Unknown sector: {sector!r}.  "
            f"Valid sectors: {sorted(SECTOR_SYMBOLS)}"
        )

    compiled = build_sector_graph()

    initial_state: SectorAnalysisState = {
        "sector": sector,
        "symbols": symbols,
        "session_id": session_id,
        "peer_results": [],
        "sector_ranking": [],
        "sector_winner": "",
        "sector_signal": "neutral",
        "fii_trend": "neutral",
        "completed": 0,
        "total": len(symbols),
    }

    result: dict[str, Any] = await compiled.ainvoke(initial_state)
    return result


__all__ = [
    "SECTOR_SYMBOLS",
    "PeerResult",
    "SectorAnalysisState",
    "analyze_single_peer",
    "aggregate_results",
    "build_sector_graph",
    "route_to_peers",
    "run_sector_analysis",
]
