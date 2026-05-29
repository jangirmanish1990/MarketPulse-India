"""Node: parse_announcement — GPT-4o-mini structured extraction from raw announcement text."""

from __future__ import annotations

import logging
import time
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig

from agents.llm import get_llm_fast
from agents.parsers import (
    BoardMeetingParsed,
    InsiderTradeParsed,
    QuarterlyResultsParsed,
    SHPParsed,
)
from agents.state import IndiaMarketState

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a financial data extraction specialist for Indian stock markets.\n"
    "Extract structured data from NSE/BSE announcements accurately.\n"
    "All monetary values must be in Indian Crores (₹ Cr).\n"
    "If a value is not mentioned, use None.\n"
    "For YoY/QoQ growth: positive = growth, negative = decline."
)

_HUMAN = (
    "Extract financial data from this NSE announcement:\n\n"
    "Company: {symbol}\n"
    "Announcement Type: {announcement_type}\n"
    "Raw Announcement Text:\n{announcement_text}\n\n"
    "Extract all available financial metrics accurately."
)

_PROMPT = ChatPromptTemplate.from_messages([("system", _SYSTEM), ("human", _HUMAN)])

_MODEL_MAP: dict[str, type] = {
    "quarterly_results": QuarterlyResultsParsed,
    "board_meeting": BoardMeetingParsed,
    "insider_trade": InsiderTradeParsed,
    "shareholding": SHPParsed,
}


async def parse_announcement(state: IndiaMarketState, config: RunnableConfig) -> dict[str, Any]:
    """Extract structured fields from raw announcement text via GPT-4o-mini.

    Routes by announcement_type → Pydantic model → state field:
      quarterly_results → parsed_quarterly + quarter_verdict
      board_meeting     → parsed_board
      insider_trade     → parsed_insider
      shareholding      → parsed_shp
      other             → no-op, returns unchanged state
    """
    start = time.monotonic()
    symbol = state["nse_symbol"]
    ann_type = state["announcement_type"]

    if ann_type == "other":
        print(f"[parse_announcement] {symbol} — type 'other', skipping parse")
        return {
            "node_timings": {
                **state["node_timings"],
                "parse_announcement": round(time.monotonic() - start, 3),
            }
        }

    model_cls = _MODEL_MAP.get(ann_type)
    if model_cls is None:
        logger.warning("[parse_announcement] Unknown type %r — skipping", ann_type)
        return {
            "node_timings": {
                **state["node_timings"],
                "parse_announcement": round(time.monotonic() - start, 3),
            }
        }

    try:
        chain = _PROMPT | get_llm_fast().with_structured_output(model_cls)
        result = await chain.ainvoke({
            "symbol": symbol,
            "announcement_type": ann_type,
            "announcement_text": state["announcement_raw"],
        })
    except Exception as exc:
        logger.error("[parse_announcement] LLM extraction failed for %s %s: %s", symbol, ann_type, exc)
        return {
            "node_timings": {
                **state["node_timings"],
                "parse_announcement": round(time.monotonic() - start, 3),
            }
        }

    elapsed_ms = round((time.monotonic() - start) * 1000)

    # ── Unpack into correct state fields ─────────────────────────────────────
    parsed_quarterly = state.get("parsed_quarterly")
    parsed_board = state.get("parsed_board")
    parsed_insider = state.get("parsed_insider")
    parsed_shp = state.get("parsed_shp")
    quarter_verdict = state.get("quarter_verdict")

    if isinstance(result, QuarterlyResultsParsed):
        parsed_quarterly = result.model_dump()
        quarter_verdict = result.beat_or_miss
        print(f"[parse_announcement] {symbol} quarterly_results parsed in {elapsed_ms}ms")
        print(
            f"[parse_announcement] Revenue: ₹{result.revenue_cr:.1f} Cr | "
            f"PAT: ₹{result.pat_cr:.1f} Cr | {result.beat_or_miss}"
        )
    elif isinstance(result, BoardMeetingParsed):
        parsed_board = result.model_dump()
        print(f"[parse_announcement] {symbol} board_meeting parsed in {elapsed_ms}ms")
    elif isinstance(result, InsiderTradeParsed):
        parsed_insider = result.model_dump()
        print(f"[parse_announcement] {symbol} insider_trade parsed in {elapsed_ms}ms")
    elif isinstance(result, SHPParsed):
        parsed_shp = result.model_dump()
        print(f"[parse_announcement] {symbol} shareholding parsed in {elapsed_ms}ms")

    return {
        "parsed_quarterly": parsed_quarterly,
        "parsed_board": parsed_board,
        "parsed_insider": parsed_insider,
        "parsed_shp": parsed_shp,
        "quarter_verdict": quarter_verdict,
        "node_timings": {
            **state["node_timings"],
            "parse_announcement": round(time.monotonic() - start, 3),
        },
    }
