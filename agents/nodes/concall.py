"""Node: concall_analyzer — fetch and analyse earnings call transcripts.

Resolution order for each symbol:
  1. Local disk cache  (data/transcripts/<SYMBOL>_latest.json)
  2. Screener.in concalls page  (returns URL; no full text)
  3. Built-in mock transcripts for INFY / TCS  (smoke-test / offline)
  4. Skip gracefully → concall_available = False

Uses gpt-4o-mini (llm_fast) — concall analysis is a structured extraction
task, not heavy reasoning.  All sync I/O is wrapped in asyncio.to_thread so
the node is safe on Windows event-loop policy.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Literal

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ConfigDict, Field

from agents.llm import llm_fast
from agents.state import IndiaMarketState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Output schema
# ---------------------------------------------------------------------------


class ConcallAnalysis(BaseModel):
    """Structured output from earnings-call transcript analysis."""

    model_config = ConfigDict(strict=True)

    management_tone: Literal["optimistic", "cautious", "defensive", "mixed"] = Field(
        description="Overall tone of management commentary"
    )

    tone_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence in tone assessment",
    )

    revenue_guidance_direction: Literal["upgrade", "maintained", "downgrade"] | None = Field(
        None,
        description="Direction of revenue guidance change",
    )

    revenue_guidance_text: str | None = Field(
        None,
        description="Exact guidance text mentioned",
    )

    key_risks_mentioned: list[str] = Field(
        default_factory=list,
        description="Specific risks management mentioned",
    )

    key_positives_mentioned: list[str] = Field(
        default_factory=list,
        description="Positive points highlighted by management",
    )

    analyst_sentiment: Literal["positive", "neutral", "negative"] = Field(
        description="Sentiment from analyst Q&A section"
    )

    # IT-specific ──────────────────────────────────────────────────────────────
    deal_wins_tcv_usd_bn: float | None = Field(
        None,
        description="Deal wins TCV in USD billions if mentioned",
    )

    # Banking-specific ─────────────────────────────────────────────────────────
    npa_outlook: Literal["improving", "stable", "deteriorating"] | None = Field(
        None,
        description="NPA outlook for banking stocks",
    )

    nim_guidance: str | None = Field(
        None,
        description="NIM guidance for banking stocks",
    )

    # Cross-check ──────────────────────────────────────────────────────────────
    tone_vs_numbers: Literal["aligned", "tone_more_cautious", "tone_more_optimistic"] = Field(
        description=(
            "Cross-check between management tone and reported numbers. "
            "tone_more_cautious: numbers beat but management sounds cautious; "
            "tone_more_optimistic: numbers missed but management sounds positive; "
            "aligned: tone matches the reported numbers."
        )
    )

    signal_adjustment: Literal["upgrade", "maintain", "downgrade"] = Field(
        description=(
            "How concall analysis should adjust the base signal. "
            "downgrade if tone_more_cautious (guidance cut or defensive tone); "
            "upgrade if tone_more_optimistic with strong deal wins; "
            "maintain if aligned."
        )
    )

    confidence_delta: float = Field(
        description=(
            "Confidence adjustment to apply to the existing signal confidence: "
            "+0.05 for upgrade, 0.0 for maintain, -0.08 for downgrade."
        )
    )


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM = """\
You are analyzing an Indian company earnings call transcript.

Your job is to extract management tone, guidance, and key themes.

For Indian IT companies focus on:
- Deal wins (TCV in USD billions) — higher = more positive
- Revenue guidance in constant currency (CC) terms
- Discretionary spend recovery commentary
- Margin trajectory and guidance

For Indian Banking companies focus on:
- NPA (Non-Performing Assets) outlook — improving is positive
- NIM (Net Interest Margin) guidance
- Credit growth commentary
- Asset quality and provision coverage

TONE ASSESSMENT RULES:
- "optimistic": strong guidance, positive outlook, beat on all metrics
- "cautious": hedging language, uncertain recovery, conservative guidance
- "defensive": missed metrics, explaining away negatives
- "mixed": some positive some negative signals

CROSS-CHECK RULE (most important):
If numbers BEAT expectations but management tone is CAUTIOUS
(uses words like: "gradual", "uncertain", "cautious", "slower than expected")
  -> set tone_vs_numbers = "tone_more_cautious"
  -> set signal_adjustment = "downgrade"
  -> set confidence_delta = -0.08

If numbers MISSED but management is OPTIMISTIC about recovery
  -> set tone_vs_numbers = "tone_more_optimistic"
  -> set signal_adjustment = "upgrade"
  -> set confidence_delta = +0.05

If tone MATCHES numbers (beat+optimistic or miss+defensive)
  -> set tone_vs_numbers = "aligned"
  -> set signal_adjustment = "maintain"
  -> set confidence_delta = 0.0

Do not use phrases like "buy" or "sell".
This is for educational purposes only.\
"""

_PROMPT: ChatPromptTemplate = ChatPromptTemplate.from_messages(
    [
        ("system", _SYSTEM),
        ("human", "Analyze this earnings call:\n\n{text}"),
    ]
)


# ---------------------------------------------------------------------------
# Helper — build transcript text for the LLM
# ---------------------------------------------------------------------------


def _build_concall_text(symbol: str, transcript: dict[str, Any], state: IndiaMarketState) -> str:
    """Assemble the prompt payload from transcript + existing state context."""
    return (
        f"Company: {symbol}\n"
        f"Quarter: {transcript.get('quarter', 'latest')}\n\n"
        "MANAGEMENT OPENING REMARKS:\n"
        f"{transcript.get('management_opening', '').strip()}\n\n"
        "ANALYST Q&A:\n"
        f"{transcript.get('analyst_qa', '').strip()}\n\n"
        "REPORTED RESULTS CONTEXT:\n"
        f"Quarter verdict: {state.get('quarter_verdict') or 'unknown'}\n"
        f"Announcement: {state.get('announcement_raw', '')[:500]}"
    )


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------


async def concall_analyzer(
    state: IndiaMarketState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Fetch and analyse an earnings call transcript for the current symbol.

    Writes into state:
        concall_available       — True iff transcript found and analysed.
        concall_tone            — Management tone enum.
        concall_signal_adjustment — Signal direction adjustment.
        confidence              — Adjusted by ConcallAnalysis.confidence_delta
                                  (only written when confidence is already set).
        node_timings            — Updated with "concall_analyzer" ms entry.
    """
    start = time.monotonic()
    symbol = state["nse_symbol"]

    print(f"[concall_analyzer] Checking transcript for {symbol}")

    # ------------------------------------------------------------------
    # 1. Fetch transcript (sync MCP tool → worker thread)
    # ------------------------------------------------------------------
    transcript: dict[str, Any] | None = None
    try:
        from mcp_servers.indian_news.server import get_concall_transcript

        transcript = await asyncio.to_thread(get_concall_transcript, symbol, "latest")
    except Exception as exc:
        logger.warning("[concall_analyzer] Transcript fetch failed for %s: %s", symbol, exc)

    if (
        not transcript
        or not transcript.get("available")
        or not transcript.get("management_opening")
    ):
        print(f"[concall_analyzer] No transcript available for {symbol}")
        return {
            "concall_available": False,
            "concall_tone": None,
            "concall_signal_adjustment": None,
            "node_timings": {
                **state["node_timings"],
                "concall_analyzer": round(time.monotonic() - start, 3),
            },
        }

    # ------------------------------------------------------------------
    # 2. Build concall text and call gpt-4o-mini
    # ------------------------------------------------------------------
    concall_text = _build_concall_text(symbol, transcript, state)

    structured_llm = llm_fast.with_structured_output(ConcallAnalysis)
    chain = _PROMPT | structured_llm

    try:
        raw: Any = await asyncio.to_thread(chain.invoke, {"text": concall_text})

        if not isinstance(raw, ConcallAnalysis):
            raise TypeError(f"Unexpected output type from structured LLM: {type(raw)}")

        result: ConcallAnalysis = raw

        # ── Apply confidence delta (only if confidence already scored) ────────
        current_conf: float | None = state.get("confidence")
        new_conf: float | None = None
        if current_conf is not None:
            new_conf = round(max(0.10, min(0.95, current_conf + result.confidence_delta)), 3)
            print(
                f"[concall_analyzer] Confidence adjusted: "
                f"{current_conf:.2f} -> {new_conf:.2f} ({result.signal_adjustment})"
            )

        elapsed_ms = round((time.monotonic() - start) * 1000)
        print(
            f"[concall_analyzer] {symbol} | "
            f"tone={result.management_tone} | "
            f"tone_vs_numbers={result.tone_vs_numbers} | "
            f"adjustment={result.signal_adjustment} | "
            f"{elapsed_ms:,}ms"
        )

        update: dict[str, Any] = {
            "concall_available": True,
            "concall_tone": result.management_tone,
            "concall_signal_adjustment": result.signal_adjustment,
            "node_timings": {
                **state["node_timings"],
                "concall_analyzer": round(time.monotonic() - start, 3),
            },
        }
        if new_conf is not None:
            update["confidence"] = new_conf
        return update

    except Exception as exc:
        logger.error("[concall_analyzer] LLM analysis failed for %s: %s", symbol, exc)
        return {
            "concall_available": False,
            "concall_tone": None,
            "concall_signal_adjustment": None,
            "node_timings": {
                **state["node_timings"],
                "concall_analyzer": round(time.monotonic() - start, 3),
            },
        }
