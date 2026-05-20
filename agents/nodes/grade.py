"""Node: grade_documents — GPT-4o-mini relevance grading for CRAG."""

from __future__ import annotations

import time
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, ConfigDict, Field

from agents.llm import llm_fast
from agents.state import IndiaMarketState

_GRADER_SYSTEM = """\
You are grading documents for relevance to an Indian stock market analysis task.

Grade each document as 'relevant' or 'irrelevant' based on whether it provides
useful context for analyzing the given announcement.

A document is RELEVANT if it:
- Contains financial data for the same or peer company
- Covers the same type of announcement (quarterly results, etc.)
- Provides sector context useful for comparison
- Contains recent Indian market data

A document is IRRELEVANT if it:
- Is about completely different companies/sectors
- Contains outdated data (>2 years old)
- Is too generic with no specific financial data\
"""


class DocumentGrade(BaseModel):
    model_config = ConfigDict(strict=True)

    relevance: Literal["relevant", "irrelevant"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


async def grade_documents(state: IndiaMarketState, config: RunnableConfig) -> dict[str, Any]:
    """Grade each retrieved document for relevance via GPT-4o-mini.

    Documents graded 'relevant' with confidence >= 0.5 pass through to
    generate_analysis. If fewer than 2 pass, the CRAG conditional edge
    routes to web_search_fallback instead.
    """
    start = time.monotonic()
    docs: list[Any] = state.get("retrieved_docs") or []  # type: ignore[assignment]

    if not docs:
        print("[grade_documents] No docs to grade — flagging for web fallback")
        return {
            "doc_grades": [],
            "used_web_fallback": False,
            "node_timings": {
                **state["node_timings"],
                "grade_documents": round(time.monotonic() - start, 3),
            },
        }

    symbol: str = state["nse_symbol"]
    announcement_type: str = state["announcement_type"]
    structured_llm = llm_fast.with_structured_output(DocumentGrade)
    grades: list[dict[str, Any]] = []

    for doc in docs:
        content_preview: str = str(doc.get("content", ""))[:500]
        try:
            grade = await structured_llm.ainvoke(
                [
                    {"role": "system", "content": _GRADER_SYSTEM},
                    {
                        "role": "user",
                        "content": (
                            f"Task: Analyze {symbol} {announcement_type} announcement\n"
                            f"Document to grade:\n{content_preview}\n\n"
                            f"Is this document relevant context for analyzing {symbol}?"
                        ),
                    },
                ]
            )
            if isinstance(grade, DocumentGrade):
                grades.append(
                    {
                        "content_preview": doc.get("content", "")[:100],
                        "relevance": grade.relevance,
                        "confidence": grade.confidence,
                        "reason": grade.reason,
                        "metadata": doc.get("metadata", {}),
                    }
                )
            else:
                grades.append(
                    {
                        "content_preview": doc.get("content", "")[:100],
                        "relevance": "irrelevant",
                        "confidence": 0.0,
                        "reason": "Unexpected LLM output type",
                        "metadata": doc.get("metadata", {}),
                    }
                )
        except Exception as exc:
            print(f"[grade_documents] Grading error: {exc}")
            grades.append(
                {
                    "content_preview": doc.get("content", "")[:100],
                    "relevance": "irrelevant",
                    "confidence": 0.0,
                    "reason": f"Grading failed: {exc}",
                    "metadata": doc.get("metadata", {}),
                }
            )

    relevant = [g for g in grades if g["relevance"] == "relevant"]
    precision_pct = len(relevant) / len(grades) * 100 if grades else 0.0
    print(
        f"[grade_documents] {len(relevant)}/{len(grades)} docs relevant "
        f"(precision: {precision_pct:.0f}%)"
    )

    return {
        "doc_grades": grades,
        "node_timings": {
            **state["node_timings"],
            "grade_documents": round(time.monotonic() - start, 3),
        },
    }
