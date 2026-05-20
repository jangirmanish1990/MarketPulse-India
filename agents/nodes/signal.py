"""Node: score_signal — produce final BUY/HOLD/SELL signal with SEBI disclaimer."""

from __future__ import annotations

import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from agents.state import IndiaMarketState

_SEBI_DISCLAIMER = (
    "⚠️ MarketPulse India is not a SEBI-registered investment advisor. "
    "Output is for educational/informational purposes only and is not "
    "investment advice. Markets carry risk; consult a registered advisor "
    "before making decisions."
)


def score_signal(state: IndiaMarketState, config: RunnableConfig) -> dict[str, Any]:
    """Score the final signal from analysis and produce a SEBI-compliant output.

    TODO: replace stub with llm_strong structured-output call:
        prompt = build_signal_prompt(state)  # include analysis_summary,
                                             # quarter_verdict, concall_tone,
                                             # fii_sentiment, nifty_change_pct,
                                             # promoter_pct, financials
        response = llm_strong.with_structured_output(SignalOutput).invoke(prompt)
        return {
            "signal_direction": response.direction,   # BUY | HOLD | SELL
            "confidence": response.confidence,        # 0.0 – 1.0
            "target_price_inr": response.target,
            "upside_pct": response.upside,
            "time_horizon_days": response.horizon,
            "rationale": response.rationale,
            "sebi_disclaimer": _SEBI_DISCLAIMER,
        }
    """
    start = time.monotonic()
    print("[score_signal] Scoring signal → HOLD (stub)")

    return {
        "signal_direction": "HOLD",
        "confidence": 0.75,
        "target_price_inr": 0.0,
        "upside_pct": None,
        "time_horizon_days": None,
        "rationale": None,
        "sebi_disclaimer": _SEBI_DISCLAIMER,
        "node_timings": {
            **state["node_timings"],
            "score_signal": round(time.monotonic() - start, 3),
        },
    }
