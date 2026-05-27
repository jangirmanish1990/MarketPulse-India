"""Node: promoter_intelligence — shareholding pattern + FII/DII flow analysis.

Fetches from bse-mcp (get_shareholding_pattern, get_fii_dii_flows) via
asyncio.to_thread so the sync MCP helpers don't block the event loop.

Writes to state
---------------
promoter_pct              float | None
promoter_pledging_pct     float | None
promoter_pledging_risk    "high" | "medium" | "low" | "none" | None
promoter_trend            "increasing" | "stable" | "decreasing" | None
fii_net_flow_cr           float
fii_sentiment             str
fii_ownership_trend       str | None
confidence                float | None  (adjusted in-place)
node_timings              dict  (updated in-place)
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from agents.state import IndiaMarketState

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Pydantic result models (used by tests / future agent introspection)          #
# --------------------------------------------------------------------------- #


class PromoterIntelligence(BaseModel):
    promoter_pct: float
    promoter_pledged_pct: float
    promoter_trend: Literal["increasing", "stable", "decreasing"]
    pledging_risk: Literal["high", "medium", "low", "none"]
    confidence_adjustment: float
    signal: Literal["positive", "neutral", "negative"]


class FIIDIIFlow(BaseModel):
    fii_net_cr: float
    dii_net_cr: float
    fii_classification: str
    dii_classification: str
    institutional_divergence: bool
    confidence_adjustment: float
    signal: Literal["positive", "neutral", "negative"]


# --------------------------------------------------------------------------- #
# Confidence adjustment helpers                                                 #
# --------------------------------------------------------------------------- #


def calculate_promoter_adjustment(
    pledging_risk: str,
    promoter_trend: str,
) -> float:
    """Return a confidence delta based on promoter pledging risk + holding trend.

    Clamped to [-0.15, +0.08].
    """
    delta = 0.0

    # Pledging risk component
    if pledging_risk == "high":
        delta -= 0.10
    elif pledging_risk == "medium":
        delta -= 0.04
    elif pledging_risk == "low":
        delta -= 0.02

    # Promoter holding trend component
    if promoter_trend == "increasing":
        delta += 0.05
    elif promoter_trend == "decreasing":
        delta -= 0.06

    return round(max(-0.15, min(0.08, delta)), 3)


def calculate_fii_adjustment(
    fii_classification: str,
    dii_classification: str,
) -> float:
    """Return a confidence delta based on FII flow classification.

    Adds a -0.03 divergence penalty when FII and DII are on opposite sides.
    Clamped to [-0.10, +0.10].
    """
    fii_map: dict[str, float] = {
        "strong_buyer": +0.07,
        "buyer": +0.04,
        "neutral": 0.0,
        "seller": -0.04,
        "strong_seller": -0.07,
    }
    delta = fii_map.get(fii_classification, 0.0)

    fii_buying = fii_classification in ("strong_buyer", "buyer")
    dii_buying = dii_classification in ("strong_buyer", "buyer")
    fii_selling = fii_classification in ("strong_seller", "seller")
    dii_selling = dii_classification in ("strong_seller", "seller")

    if (fii_buying and dii_selling) or (fii_selling and dii_buying):
        delta -= 0.03  # divergence uncertainty penalty

    return round(max(-0.10, min(0.10, delta)), 3)


# --------------------------------------------------------------------------- #
# Node                                                                          #
# --------------------------------------------------------------------------- #


async def promoter_intelligence(
    state: IndiaMarketState,
    config: RunnableConfig,
) -> IndiaMarketState:
    """Enrich state with promoter shareholding + institutional flow intelligence.

    Data flow
    ---------
    1. Call get_shareholding_pattern(symbol) via asyncio.to_thread
    2. Call get_fii_dii_flows("all") via asyncio.to_thread
    3. Compute confidence adjustments and apply to state["confidence"]
    4. Write all institutional fields to state
    5. Record elapsed time in state["node_timings"]

    On any exception the original state is returned unchanged (graceful fallback).
    """
    symbol: str = state["nse_symbol"]
    start = time.time()

    print(f"[promoter_intelligence] Fetching SHP for {symbol}")

    # ── 1. Fetch data from bse-mcp helpers ──────────────────────────────── #
    shp: dict[str, Any] = {}
    flows: dict[str, Any] = {}
    try:
        from mcp_servers.bse.server import (  # noqa: PLC0415
            get_fii_dii_flows,
            get_shareholding_pattern,
        )

        shp, flows = await asyncio.gather(
            asyncio.to_thread(get_shareholding_pattern, symbol),
            asyncio.to_thread(get_fii_dii_flows, "all"),
        )
    except Exception as exc:
        logger.warning(
            "[promoter_intelligence] Fetch failed for %s: %s — returning state unchanged",
            symbol,
            exc,
        )
        print(f"[promoter_intelligence] Fetch failed: {exc}")
        return state

    # ── 2. Process promoter data ─────────────────────────────────────────── #
    pledging_risk: str = shp.get("pledging_risk", "none")
    promoter_pct: float = float(shp.get("promoter_pct", 0.0))
    promoter_trend: str = "stable"  # Week 5 will add historical SHP tracking

    promoter_adj = calculate_promoter_adjustment(pledging_risk, promoter_trend)

    # ── 3. Process FII/DII data ──────────────────────────────────────────── #
    fii_class: str = flows.get("fii_classification", "neutral")
    dii_class: str = flows.get("dii_classification", "neutral")
    fii_adj = calculate_fii_adjustment(fii_class, dii_class)

    # ── 4. Write institutional fields to state ───────────────────────────── #
    state["promoter_pct"] = promoter_pct
    state["promoter_pledging_pct"] = float(shp.get("promoter_pledged_pct", 0.0))
    state["promoter_pledging_risk"] = pledging_risk  # type: ignore[typeddict-item]
    state["promoter_trend"] = promoter_trend  # type: ignore[typeddict-item]
    state["fii_net_flow_cr"] = float(flows.get("fii_net_cr", 0.0))
    state["fii_sentiment"] = fii_class  # type: ignore[typeddict-item]
    state["fii_ownership_trend"] = f"FII {fii_class} | DII {dii_class}"

    # ── 5. Apply combined confidence adjustment ──────────────────────────── #
    total_adj = round(promoter_adj + fii_adj, 3)
    old_conf: float | None = state.get("confidence")
    if old_conf is not None:
        new_conf = round(max(0.10, min(0.95, old_conf + total_adj)), 3)
        state["confidence"] = new_conf
        print(
            f"[promoter_intelligence] Confidence: "
            f"{old_conf:.2f} → {new_conf:.2f} "
            f"(promoter: {promoter_adj:+.3f}, FII: {fii_adj:+.3f})"
        )

    # ── 6. Record timing ─────────────────────────────────────────────────── #
    elapsed = int((time.time() - start) * 1000)
    state["node_timings"]["promoter_intelligence"] = elapsed

    print(
        f"[promoter_intelligence] {symbol} — "
        f"pledging={pledging_risk} "
        f"({shp.get('promoter_pledged_pct', 0):.1f}%) | "
        f"FII={fii_class} | DII={dii_class} | "
        f"adj={total_adj:+.3f} | {elapsed}ms"
    )

    return state


__all__ = [
    "FIIDIIFlow",
    "PromoterIntelligence",
    "calculate_fii_adjustment",
    "calculate_promoter_adjustment",
    "promoter_intelligence",
]
