"""Node: generate_analysis — gpt-4o structured financial analysis for Indian stocks."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ConfigDict, Field

from agents.llm import llm_strong
from agents.state import IndiaMarketState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


class FinancialAnalysis(BaseModel):
    model_config = ConfigDict(strict=True)

    summary: str = Field(
        description="3-4 sentence executive summary of the announcement and its market significance. "
        "All monetary values in ₹ Crores. Do NOT use the words 'buy' or 'sell'."
    )
    key_positives: list[str] = Field(
        description="3-5 specific positive points, each citing ₹ numbers where available."
    )
    key_risks: list[str] = Field(
        description="3-5 risk factors. At least one must be India-specific "
        "(macro, RBI policy, INR, GST, regulatory, monsoon, etc.)."
    )
    quarter_verdict: Literal["beat", "in-line", "miss"] = Field(
        description="Did results beat, meet, or miss street estimates?"
    )
    sector_outlook: Literal["bullish", "neutral", "bearish"] = Field(
        description="Near-term sector outlook based on results and macro context."
    )
    management_tone: Literal["confident", "cautious", "defensive", "mixed"] = Field(
        description="Management tone inferred from guidance and commentary."
    )
    india_macro_impact: str = Field(
        description="One sentence on how Indian macro factors (RBI, INR, FII flows, "
        "Nifty trend) affect this stock's near-term outlook."
    )
    vs_peers: str = Field(
        description="One sentence comparing performance vs sector peers based on "
        "the historical context provided."
    )
    sentiment_score: float = Field(
        ge=-1.0,
        le=1.0,
        description="Overall sentiment: -1.0 (very negative) to +1.0 (very positive). "
        "0.0 is neutral.",
    )


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM = """\
You are a senior Indian equity analyst producing structured research for NSE/BSE listed stocks.

RULES — follow strictly:
1. All monetary values in ₹ Crores (Cr) unless explicitly stated otherwise.
2. Do NOT use the words "buy" or "sell" anywhere in your output.
3. Output is for educational and informational purposes only, not investment advice.
4. For IT stocks: mention USD/INR exchange rate impact on revenue and margins.
5. For Banking stocks: explicitly address NPA (Non-Performing Assets), Net Interest Margin (NIM), and credit growth.
6. key_risks must include AT LEAST ONE India-specific risk: RBI rate action, INR depreciation, GST/regulatory change, monsoon impact, FII outflows, or capex slowdown.
7. Base quarter_verdict on analyst estimate comparisons in the announcement; default to "in-line" if estimates are not mentioned.
8. sentiment_score must be a float between -1.0 and +1.0, calibrated to magnitude of beat/miss and management tone.
9. vs_peers must reference at least one peer company by name from the historical context.
10. india_macro_impact must mention Nifty trend, FII flow sentiment, or USD/INR — whichever is most relevant.\
"""


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------


def _build_context(state: IndiaMarketState) -> str:
    """Assemble a rich analyst briefing from all available state fields."""
    symbol = state["nse_symbol"]
    ann_type = state["announcement_type"]
    lines: list[str] = []

    # ── Announcement ────────────────────────────────────────────────────────
    lines.append(f"STOCK: {symbol}  |  ANNOUNCEMENT TYPE: {ann_type}")
    lines.append("")
    lines.append("RAW ANNOUNCEMENT:")
    lines.append(state["announcement_raw"].strip())

    # ── Structured parsed data ───────────────────────────────────────────────
    parsed: dict[str, Any] | None = (
        state.get("parsed_quarterly")
        or state.get("parsed_board")
        or state.get("parsed_insider")
        or state.get("parsed_shp")
    )  # type: ignore[assignment]
    if parsed:
        lines.append("")
        lines.append("STRUCTURED PARSED DATA:")
        lines.append(json.dumps(parsed, indent=2, ensure_ascii=False))

    # ── Market context ───────────────────────────────────────────────────────
    lines.append("")
    lines.append("INDIA MARKET CONTEXT (IST):")
    lines.append(
        f"  Nifty 50        : {state['nifty_value']:,.0f} ({state['nifty_change_pct']:+.2f}%)"
    )
    lines.append(
        f"  FII Net Flow    : ₹{state['fii_net_flow_cr']:+,.0f} Cr — Sentiment: {state['fii_sentiment']}"
    )
    lines.append(f"  Sector Index    : {state['sector_index_change_pct']:+.2f}%")
    lines.append(f"  USD/INR         : {state['usd_inr']:.2f} — {state['usd_inr_context']}")
    lines.append(f"  Market Status   : {state['market_status']}")

    # ── Live quote ───────────────────────────────────────────────────────────
    quote: dict[str, Any] = state.get("live_quote") or {}  # type: ignore[assignment]
    if quote:
        price = quote.get("current_price") or quote.get("lastPrice") or quote.get("close") or 0.0
        chg = quote.get("change_pct") or quote.get("pChange") or 0.0
        if price:
            lines.append(f"  Current Price   : ₹{price:,.2f} ({chg:+.2f}%)")

    # ── Concall intelligence (optional) ─────────────────────────────────────
    concall_tone = state.get("concall_tone")  # type: ignore[assignment]
    if concall_tone:
        lines.append("")
        lines.append("CONCALL INTELLIGENCE:")
        lines.append(f"  Tone              : {concall_tone}")
        if state.get("concall_guidance_cr"):
            lines.append(f"  Guidance (₹ Cr)   : {state['concall_guidance_cr']:,.0f}")
        if state.get("concall_signal_adjustment"):
            lines.append(f"  Signal Adjustment : {state['concall_signal_adjustment']}")

    # ── Graded historical docs (top 4 relevant only) ─────────────────────────
    grades: list[Any] = state.get("doc_grades") or []  # type: ignore[assignment]
    relevant_docs = [g for g in grades if isinstance(g, dict) and g.get("relevance") == "relevant"][
        :4
    ]

    if relevant_docs:
        lines.append("")
        lines.append("HISTORICAL CONTEXT (graded relevant by CRAG):")
        for i, doc in enumerate(relevant_docs, 1):
            meta = doc.get("metadata", {})
            peer = meta.get("nse_symbol", "?")
            quarter = meta.get("quarter", "")
            preview = doc.get("content_preview", "")[:200]
            lines.append(f"  [{i}] {peer} {quarter}: {preview}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------


async def generate_analysis(state: IndiaMarketState, config: RunnableConfig) -> dict[str, Any]:
    """Synthesize announcement, market context, and CRAG docs into analysis.

    Calls gpt-4o with structured output to produce a FinancialAnalysis.
    Gracefully degrades to stub values on any LLM or parsing error.
    """
    start = time.monotonic()
    symbol = state["nse_symbol"]
    ann_type = state["announcement_type"]

    context = _build_context(state)

    structured_llm = llm_strong.with_structured_output(FinancialAnalysis)

    try:
        result = await asyncio.to_thread(
            structured_llm.invoke,
            [
                {"role": "system", "content": _SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"Produce a comprehensive analysis for the following "
                        f"Indian stock announcement:\n\n{context}"
                    ),
                },
            ],
        )

        if not isinstance(result, FinancialAnalysis):
            raise TypeError(f"Unexpected output type: {type(result)}")

        elapsed_ms = round((time.monotonic() - start) * 1000)
        print(
            f"[generate_analysis] {symbol} {ann_type} | "
            f"verdict={result.quarter_verdict} | "
            f"sentiment={result.sentiment_score:+.2f} | "
            f"{elapsed_ms:,}ms"
        )

        return {
            "analysis_summary": result.summary,
            "key_positives": result.key_positives,
            "key_risks": result.key_risks,
            "quarter_verdict": result.quarter_verdict,
            "sector_outlook": result.sector_outlook,
            "node_timings": {
                **state["node_timings"],
                "generate_analysis": round(time.monotonic() - start, 3),
            },
        }

    except Exception as exc:
        logger.error(
            "[generate_analysis] LLM call failed for %s %s: %s",
            symbol,
            ann_type,
            exc,
        )
        elapsed_ms = round((time.monotonic() - start) * 1000)
        print(f"[generate_analysis] {symbol} ERROR after {elapsed_ms:,}ms: {exc}")

        # Degrade gracefully — downstream score_signal can still run
        return {
            "analysis_summary": f"Analysis unavailable for {symbol} ({ann_type}).",
            "key_positives": [],
            "key_risks": [],
            "quarter_verdict": state.get("quarter_verdict"),  # type: ignore[typeddict-item]
            "sector_outlook": None,
            "node_timings": {
                **state["node_timings"],
                "generate_analysis": round(time.monotonic() - start, 3),
            },
        }
