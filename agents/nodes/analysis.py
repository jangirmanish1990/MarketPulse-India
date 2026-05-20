"""Node: generate_analysis — synthesize all context into a structured analysis."""

from __future__ import annotations

import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from agents.state import IndiaMarketState


def generate_analysis(state: IndiaMarketState, config: RunnableConfig) -> dict[str, Any]:
    """Synthesize parsed announcement, market context, and docs into analysis.

    TODO: replace stub with llm_strong structured-output call:
        prompt = build_analysis_prompt(state)  # include parsed_quarterly,
                                               # retrieved_docs, nifty context,
                                               # concall_tone, fii_sentiment
        response = llm_strong.with_structured_output(AnalysisOutput).invoke(prompt)
        return {
            "analysis_summary": response.summary,
            "key_positives": response.positives,
            "key_risks": response.risks,
            "quarter_verdict": response.verdict,  # beat / in-line / miss
            "sector_outlook": response.sector_outlook,
        }
    """
    start = time.monotonic()
    print("[generate_analysis] Generating analysis")

    return {
        "analysis_summary": f"Stub analysis for {state['nse_symbol']}",
        "key_positives": None,
        "key_risks": None,
        "quarter_verdict": None,
        "sector_outlook": None,
        "node_timings": {
            **state["node_timings"],
            "generate_analysis": round(time.monotonic() - start, 3),
        },
    }
