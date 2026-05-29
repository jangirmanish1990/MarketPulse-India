"""Node: score_signal — GPT-4o BUY/HOLD/SELL signal with India adjustments."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ConfigDict, Field, field_validator

from agents.llm import get_llm_strong
from agents.state import IndiaMarketState

logger = logging.getLogger(__name__)

_SEBI_DISCLAIMER = (
    "Warning: MarketPulse India is not a SEBI-registered investment advisor. "
    "Output is for educational and informational purposes only and is not "
    "investment advice. Markets carry risk; consult a registered advisor "
    "before making decisions."
)

# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


class IndianSignal(BaseModel):
    model_config = ConfigDict(strict=True)

    direction: Literal["BUY", "HOLD", "SELL"]
    base_confidence: float = Field(ge=0.10, le=0.95)
    target_price_inr: float = Field(gt=0.0)
    time_horizon_days: int = Field(description="Must be 30, 60, or 90")
    rationale: str = Field(description="1-2 sentences with key trigger")
    key_trigger: str = Field(description="Single most important factor driving the signal")

    @field_validator("time_horizon_days")
    @classmethod
    def validate_horizon(cls, v: int) -> int:
        if v not in (30, 60, 90):
            # Round to nearest valid horizon rather than rejecting
            if v <= 45:
                return 30
            if v <= 75:
                return 60
            return 90
        return v


# ---------------------------------------------------------------------------
# India-specific confidence adjustments
# ---------------------------------------------------------------------------


def apply_india_adjustments(base_confidence: float, state: IndiaMarketState) -> float:
    """Apply India-specific adjustments to LLM base_confidence.

    Each adjustment that fires is printed. Final value is clamped [0.10, 0.95].
    """
    adj = base_confidence
    symbol = state["nse_symbol"]

    # ── Quarterly verdict ────────────────────────────────────────────────────
    verdict = state.get("quarter_verdict")  # type: ignore[assignment]
    if verdict == "beat":
        adj += 0.08
        print(f"[score_signal] {symbol}  quarter_beat        : +0.08 → {adj:.2f}")
    elif verdict == "miss":
        adj -= 0.12
        print(f"[score_signal] {symbol}  quarter_miss        : -0.12 → {adj:.2f}")

    # ── FII sentiment ────────────────────────────────────────────────────────
    fii = state["fii_sentiment"]
    if fii == "strong_buyer":
        adj += 0.07
        print(f"[score_signal] {symbol}  fii_strong_buyer    : +0.07 → {adj:.2f}")
    elif fii == "buyer":
        adj += 0.04
        print(f"[score_signal] {symbol}  fii_buyer           : +0.04 → {adj:.2f}")
    elif fii == "strong_seller":
        adj -= 0.07
        print(f"[score_signal] {symbol}  fii_strong_seller   : -0.07 → {adj:.2f}")
    elif fii == "seller":
        adj -= 0.04
        print(f"[score_signal] {symbol}  fii_seller          : -0.04 → {adj:.2f}")

    # ── Promoter pledging ────────────────────────────────────────────────────
    pledging_risk = state.get("promoter_pledging_risk")  # type: ignore[assignment]
    if pledging_risk == "high":
        adj -= 0.10
        print(f"[score_signal] {symbol}  promoter_pledge_high: -0.10 → {adj:.2f}")
    elif pledging_risk == "medium":
        adj -= 0.04
        print(f"[score_signal] {symbol}  promoter_pledge_med : -0.04 → {adj:.2f}")

    # ── Promoter trend ───────────────────────────────────────────────────────
    promoter_trend = state.get("promoter_trend")  # type: ignore[assignment]
    if promoter_trend == "increasing":
        adj += 0.05
        print(f"[score_signal] {symbol}  promoter_increasing : +0.05 → {adj:.2f}")
    elif promoter_trend == "decreasing":
        adj -= 0.06
        print(f"[score_signal] {symbol}  promoter_decreasing : -0.06 → {adj:.2f}")

    # ── RAG quality penalty ──────────────────────────────────────────────────
    if state.get("used_web_fallback"):
        adj -= 0.05
        print(f"[score_signal] {symbol}  web_fallback_used   : -0.05 → {adj:.2f}")

    # ── Nifty momentum ───────────────────────────────────────────────────────
    nifty_chg = state["nifty_change_pct"]
    if nifty_chg > 1.0:
        adj += 0.03
        print(f"[score_signal] {symbol}  nifty_bull(>{1:.0f}%)    : +0.03 → {adj:.2f}")
    elif nifty_chg < -1.0:
        adj -= 0.03
        print(f"[score_signal] {symbol}  nifty_bear(<-{1:.0f}%)   : -0.03 → {adj:.2f}")

    final = round(max(0.10, min(0.95, adj)), 4)
    print(
        f"[score_signal] {symbol}  final_confidence    : {final:.2f}  (base={base_confidence:.2f})"
    )
    return final


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM = """\
You are a decisive quantitative signal generator for Indian NSE/BSE stocks.

You MUST generate differentiated signals.
Do NOT default to HOLD for everything.

STRICT RULES:

Generate BUY when ALL of these are true:
- Results beat estimates (quarter_verdict = beat)
- Revenue growth > 5% YoY
- Management tone is confident or mixed
- Sector outlook is bullish or neutral
- No major governance risks

Generate SELL when ANY of these is true:
- Revenue declined YoY
- PAT declined YoY
- Guidance was cut or is negative
- Management tone is defensive
- Results missed badly

Generate HOLD when:
- Results were in-line (not beat, not miss)
- Mixed signals with no clear direction
- Beat on one metric but miss on another

IMPORTANT: If results clearly beat estimates with strong numbers, signal MUST be BUY.
If revenue declined YoY, signal MUST be SELL.
Do NOT be overly cautious.

Price target rules:
- BUY:  target = current_price * 1.12 to 1.20
- SELL: target = current_price * 0.85 to 0.92
- HOLD: target = current_price * 0.98 to 1.03

Time horizon (choose ONLY 30, 60, or 90 — no other values):
- BUY with strong beat: 30 days
- BUY with moderate beat: 60 days
- HOLD: 90 days
- SELL: 30 days

MANDATORY:
- base_confidence must be between 0.10 and 0.95.
- key_trigger must name the single most important factor (e.g. "Revenue beat +10% YoY").
- This is for educational purposes only, not investment advice.\
"""


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------


def _build_signal_context(state: IndiaMarketState, current_price: float) -> str:
    lines: list[str] = []
    symbol = state["nse_symbol"]

    lines.append(f"STOCK: {symbol}  |  CURRENT PRICE: ₹{current_price:,.2f}")
    lines.append("")

    # Analysis output
    if state.get("analysis_summary"):
        lines.append(f"ANALYSIS SUMMARY:\n{state['analysis_summary']}")
        lines.append("")

    positives: list[Any] = state.get("key_positives") or []  # type: ignore[assignment]
    if positives:
        lines.append("KEY POSITIVES:")
        for p in positives:
            lines.append(f"  + {p}")
        lines.append("")

    risks: list[Any] = state.get("key_risks") or []  # type: ignore[assignment]
    if risks:
        lines.append("KEY RISKS:")
        for r in risks:
            lines.append(f"  - {r}")
        lines.append("")

    lines.append("SIGNAL INPUTS:")
    lines.append(f"  Quarter Verdict : {state.get('quarter_verdict') or 'unknown'}")
    lines.append(f"  Sector Outlook  : {state.get('sector_outlook') or 'unknown'}")
    lines.append(f"  Concall Tone    : {state.get('concall_tone') or 'not available'}")
    if state.get("concall_signal_adjustment"):
        lines.append(f"  Concall Adj     : {state['concall_signal_adjustment']}")
    lines.append(f"  FII Sentiment   : {state['fii_sentiment']}")
    lines.append(f"  Nifty Change    : {state['nifty_change_pct']:+.2f}%")
    lines.append(f"  USD/INR         : {state['usd_inr']:.2f}")

    if state.get("promoter_pct") is not None:
        lines.append(f"  Promoter Holding: {state['promoter_pct']:.1f}%")
    if state.get("promoter_pledging_risk"):
        lines.append(f"  Pledging Risk   : {state['promoter_pledging_risk']}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Price resolver
# ---------------------------------------------------------------------------


def _resolve_price(state: IndiaMarketState) -> float:
    """Extract current price from live_quote, or fall back to yfinance history."""
    quote: dict[str, Any] = state.get("live_quote") or {}  # type: ignore[assignment]

    for key in ("ltp", "lastPrice", "current_price", "close"):
        val = quote.get(key)
        if val and float(val) > 0:
            return float(val)

    # Fallback: last close from yfinance price history
    history: dict[str, Any] = state.get("price_history") or {}  # type: ignore[assignment]
    closes: list[float] = history.get("closes") or []
    if closes and closes[-1] > 0:
        logger.info("[score_signal] Using price_history fallback for %s", state["nse_symbol"])
        return float(closes[-1])

    # Last resort: live fetch from yfinance MCP
    try:
        from mcp_servers.yfinance_india.server import get_price_history

        hist = get_price_history(state["nse_symbol"], period="5d")
        hist_closes: list[float] = hist.get("closes") or []
        if hist_closes and hist_closes[-1] > 0:
            logger.info(
                "[score_signal] Fetched fallback price for %s via yfinance", state["nse_symbol"]
            )
            return float(hist_closes[-1])
    except Exception:
        logger.warning("[score_signal] yfinance fallback failed for %s", state["nse_symbol"])

    return 0.0


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------


async def score_signal(state: IndiaMarketState, config: RunnableConfig) -> dict[str, Any]:
    """Produce a BUY/HOLD/SELL signal using GPT-4o then apply India adjustments.

    Saves the signal to PostgreSQL via SignalRepo. SEBI disclaimer is always set.
    Gracefully degrades to HOLD / 0.50 confidence on any failure.
    """
    start = time.monotonic()
    symbol = state["nse_symbol"]

    # ── Resolve current price ────────────────────────────────────────────────
    current_price = _resolve_price(state)
    if current_price == 0.0:
        logger.warning("[score_signal] Could not resolve price for %s — using 0", symbol)

    # ── LLM signal generation ────────────────────────────────────────────────
    direction: Literal["BUY", "HOLD", "SELL"] = "HOLD"
    confidence: float = 0.50
    target_price: float = current_price
    horizon: int = 90
    rationale: str = f"Signal unavailable for {symbol}."
    key_trigger: str = "Analysis error"

    try:
        context = _build_signal_context(state, current_price)
        structured_llm = get_llm_strong().with_structured_output(IndianSignal)

        raw: Any = await asyncio.to_thread(
            structured_llm.invoke,
            [
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": (f"Generate a signal for the following Indian stock:\n\n{context}"),
                },
            ],
        )

        if not isinstance(raw, IndianSignal):
            raise TypeError(f"Unexpected output type: {type(raw)}")

        signal: IndianSignal = raw
        direction = signal.direction
        target_price = round(signal.target_price_inr, 2)
        horizon = signal.time_horizon_days
        rationale = signal.rationale

        # ── India confidence adjustments ─────────────────────────────────────
        confidence = apply_india_adjustments(signal.base_confidence, state)
        key_trigger = signal.key_trigger
        print(f"[score_signal] {symbol}  key_trigger         : {key_trigger}")

    except Exception as exc:
        logger.error("[score_signal] LLM failed for %s: %s", symbol, exc)
        print(f"[score_signal] {symbol} ERROR: {exc} — defaulting to HOLD/0.50")

    # ── Derived metrics ──────────────────────────────────────────────────────
    upside_pct: float | None = None
    if current_price > 0 and target_price > 0:
        upside_pct = round((target_price - current_price) / current_price * 100, 2)

    # ── Print summary ────────────────────────────────────────────────────────
    upside_str = f"{upside_pct:+.1f}%" if upside_pct is not None else "n/a"
    print(
        f"[score_signal] {symbol} | {direction} | "
        f"target ₹{target_price:,.2f} | upside {upside_str} | "
        f"conf {confidence:.0%}"
    )

    # ── Persist to PostgreSQL ────────────────────────────────────────────────
    if state.get("session_id", "").startswith("eval-"):
        logger.debug("[score_signal] DB save skipped (eval mode) for %s", symbol)
    else:
        try:
            from backend.database import get_session_factory
            from backend.repositories import SignalRepo

            session_uuid = (
                uuid.UUID(state["session_id"]) if state.get("session_id") else uuid.uuid4()
            )
            async with get_session_factory()() as db_session:
                repo = SignalRepo(db_session)
                await repo.create(
                    session_id=session_uuid,
                    nse_symbol=symbol,
                    direction=direction,
                    confidence=confidence,
                    current_price_inr=current_price if current_price > 0 else None,
                    target_price_inr=target_price if target_price > 0 else None,
                    upside_pct=upside_pct,
                    time_horizon_days=horizon,
                    rationale=rationale,
                )
                await db_session.commit()
            print(f"[score_signal] {symbol} signal saved to DB")
        except Exception as exc:
            logger.warning("[score_signal] DB save failed for %s: %s", symbol, exc)

    return {
        "signal_direction": direction,
        "confidence": confidence,
        "current_price_inr": current_price if current_price > 0 else None,
        "target_price_inr": target_price if target_price > 0 else None,
        "upside_pct": upside_pct,
        "time_horizon_days": horizon,
        "rationale": rationale,
        "sebi_disclaimer": _SEBI_DISCLAIMER,
        "node_timings": {
            **state["node_timings"],
            "score_signal": round(time.monotonic() - start, 3),
        },
    }
