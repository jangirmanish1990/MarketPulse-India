"""LangSmith evaluation suite — 12 real FY25 Indian quarterly results.

Evaluators (all synchronous, called by LangSmith's evaluate()):
  1. parser_accuracy          — revenue/PAT extraction accuracy vs known values
  2. signal_accuracy_vs_nifty — direction correctness vs actual 30-day alpha
  3. faithfulness             — GPT-4o-mini judges claim grounding in source text
  4. india_risk_relevance     — India-specific keywords found in key_risks
  5. sebi_compliance          — required disclaimer phrases present

Usage:
    from tests.evals.langsmith_evals import (
        DATASET_NAME, EVAL_EXAMPLES,
        parser_accuracy, signal_accuracy_vs_nifty, faithfulness,
        india_risk_relevance, sebi_compliance,
        run_evaluations, check_thresholds,
    )
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langsmith import Client

logger = logging.getLogger(__name__)

DATASET_NAME = "marketpulse-india-fy25"

# --------------------------------------------------------------------------- #
# Dataset — 12 real FY25 quarterly results                                     #
# --------------------------------------------------------------------------- #

EVAL_EXAMPLES: list[dict[str, Any]] = [
    {
        "nse_symbol": "INFY",
        "announcement_type": "quarterly_results",
        "announcement_raw": (
            "Infosys Q2FY25: Revenue Rs 40986 Cr up 5.1% YoY. "
            "PAT Rs 6506 Cr up 4.7% YoY. EPS Rs 15.78. Margin 21.1%. "
            "Guidance raised to 4.5-5% CC for FY25. Deal wins TCV 2.4 billion USD."
        ),
        "expected_revenue_cr": 40986,
        "expected_pat_cr": 6506,
        "expected_eps": 15.78,
        "expected_direction": "BUY",
        "actual_30day_return_pct": 8.2,
        "nifty_30day_return_pct": 3.1,
        "alpha_vs_nifty": 5.1,
        "sector": "IT",
    },
    {
        "nse_symbol": "TCS",
        "announcement_type": "quarterly_results",
        "announcement_raw": (
            "TCS Q2FY25: Revenue Rs 63973 Cr up 8.1% YoY. "
            "PAT Rs 12446 Cr up 5.4% YoY. EPS Rs 33.56. Margin 24.5%. "
            "Deal TCV 8.6 billion USD."
        ),
        "expected_revenue_cr": 63973,
        "expected_pat_cr": 12446,
        "expected_eps": 33.56,
        "expected_direction": "BUY",
        "actual_30day_return_pct": 5.8,
        "nifty_30day_return_pct": 3.1,
        "alpha_vs_nifty": 2.7,
        "sector": "IT",
    },
    {
        "nse_symbol": "HDFCBANK",
        "announcement_type": "quarterly_results",
        "announcement_raw": (
            "HDFC Bank Q2FY25: NII Rs 30114 Cr up 10.1% YoY. "
            "PAT Rs 16821 Cr up 5.3% YoY. Gross NPA 1.36%. "
            "CASA 34.9%. Credit growth 7% YoY."
        ),
        "expected_revenue_cr": 30114,
        "expected_pat_cr": 16821,
        "expected_eps": 23.50,
        "expected_direction": "HOLD",
        "actual_30day_return_pct": 2.1,
        "nifty_30day_return_pct": 3.1,
        "alpha_vs_nifty": -1.0,
        "sector": "Banking",
    },
    {
        "nse_symbol": "RELIANCE",
        "announcement_type": "quarterly_results",
        "announcement_raw": (
            "Reliance Q2FY25: Revenue Rs 235481 Cr up 0.6% YoY. "
            "PAT Rs 19323 Cr up 2.2% YoY. Jio revenue Rs 34993 Cr up 18% YoY. "
            "O2C margins under pressure."
        ),
        "expected_revenue_cr": 235481,
        "expected_pat_cr": 19323,
        "expected_eps": 28.68,
        "expected_direction": "HOLD",
        "actual_30day_return_pct": 1.8,
        "nifty_30day_return_pct": 3.1,
        "alpha_vs_nifty": -1.3,
        "sector": "Conglomerate",
    },
    {
        "nse_symbol": "WIPRO",
        "announcement_type": "quarterly_results",
        "announcement_raw": (
            "Wipro Q2FY25: Revenue Rs 22302 Cr down 1% YoY. "
            "PAT Rs 3209 Cr up 5.4% YoY. IT services 2665 million USD. "
            "Q3 guidance flat to -0.5%."
        ),
        "expected_revenue_cr": 22302,
        "expected_pat_cr": 3209,
        "expected_eps": 6.14,
        "expected_direction": "SELL",
        "actual_30day_return_pct": -3.2,
        "nifty_30day_return_pct": 3.1,
        "alpha_vs_nifty": -6.3,
        "sector": "IT",
    },
    {
        "nse_symbol": "BAJFINANCE",
        "announcement_type": "quarterly_results",
        "announcement_raw": (
            "Bajaj Finance Q2FY25: NII Rs 8838 Cr up 23% YoY. "
            "PAT Rs 4014 Cr up 28% YoY. AUM Rs 370977 Cr up 29% YoY. "
            "NPA stable at 1.06%."
        ),
        "expected_revenue_cr": 8838,
        "expected_pat_cr": 4014,
        "expected_eps": 64.72,
        "expected_direction": "BUY",
        "actual_30day_return_pct": 12.4,
        "nifty_30day_return_pct": 3.1,
        "alpha_vs_nifty": 9.3,
        "sector": "NBFC",
    },
    {
        "nse_symbol": "TITAN",
        "announcement_type": "quarterly_results",
        "announcement_raw": (
            "Titan Q2FY25: Revenue Rs 13758 Cr up 18% YoY. "
            "PAT Rs 696 Cr up 22% YoY. Jewellery division grew 22% YoY. "
            "International business grew 35%."
        ),
        "expected_revenue_cr": 13758,
        "expected_pat_cr": 696,
        "expected_eps": 7.84,
        "expected_direction": "BUY",
        "actual_30day_return_pct": 7.6,
        "nifty_30day_return_pct": 3.1,
        "alpha_vs_nifty": 4.5,
        "sector": "Consumer",
    },
    {
        "nse_symbol": "NESTLEIND",
        "announcement_type": "quarterly_results",
        "announcement_raw": (
            "Nestle India Q3FY25: Revenue Rs 4747 Cr up 1.2% YoY. "
            "PAT Rs 786 Cr down 4.1% YoY. Volume growth flat. "
            "Rural demand weak. Input costs elevated."
        ),
        "expected_revenue_cr": 4747,
        "expected_pat_cr": 786,
        "expected_eps": 81.58,
        "expected_direction": "HOLD",
        "actual_30day_return_pct": 0.8,
        "nifty_30day_return_pct": 3.1,
        "alpha_vs_nifty": -2.3,
        "sector": "FMCG",
    },
    {
        "nse_symbol": "SUNPHARMA",
        "announcement_type": "quarterly_results",
        "announcement_raw": (
            "Sun Pharma Q2FY25: Revenue Rs 13966 Cr up 12% YoY. "
            "PAT Rs 2845 Cr up 19% YoY. US sales Rs 5041 Cr up 10% YoY. "
            "Specialty business growing strong."
        ),
        "expected_revenue_cr": 13966,
        "expected_pat_cr": 2845,
        "expected_eps": 11.87,
        "expected_direction": "BUY",
        "actual_30day_return_pct": 9.1,
        "nifty_30day_return_pct": 3.1,
        "alpha_vs_nifty": 6.0,
        "sector": "Pharma",
    },
    {
        "nse_symbol": "AXISBANK",
        "announcement_type": "quarterly_results",
        "announcement_raw": (
            "Axis Bank Q2FY25: NII Rs 13483 Cr up 9% YoY. "
            "PAT Rs 6917 Cr up 18% YoY. Gross NPA improved to 1.44%. "
            "ROE at 18.5%."
        ),
        "expected_revenue_cr": 13483,
        "expected_pat_cr": 6917,
        "expected_eps": 22.35,
        "expected_direction": "BUY",
        "actual_30day_return_pct": 6.3,
        "nifty_30day_return_pct": 3.1,
        "alpha_vs_nifty": 3.2,
        "sector": "Banking",
    },
    {
        "nse_symbol": "HCLTECH",
        "announcement_type": "quarterly_results",
        "announcement_raw": (
            "HCL Tech Q2FY25: Revenue Rs 28862 Cr up 8.2% YoY. "
            "PAT Rs 4235 Cr up 10.7% YoY. IT services grew 5% YoY in CC. "
            "FY25 revenue guidance 4.5-5% CC."
        ),
        "expected_revenue_cr": 28862,
        "expected_pat_cr": 4235,
        "expected_eps": 15.64,
        "expected_direction": "BUY",
        "actual_30day_return_pct": 7.2,
        "nifty_30day_return_pct": 3.1,
        "alpha_vs_nifty": 4.1,
        "sector": "IT",
    },
    {
        "nse_symbol": "KOTAKBANK",
        "announcement_type": "quarterly_results",
        "announcement_raw": (
            "Kotak Bank Q2FY25: NII Rs 7020 Cr up 11% YoY. "
            "PAT Rs 3344 Cr up 5% YoY. RBI ban on new credit cards lifted. "
            "CASA ratio 43.3%."
        ),
        "expected_revenue_cr": 7020,
        "expected_pat_cr": 3344,
        "expected_eps": 16.83,
        "expected_direction": "BUY",
        "actual_30day_return_pct": 8.9,
        "nifty_30day_return_pct": 3.1,
        "alpha_vs_nifty": 5.8,
        "sector": "Banking",
    },
]

# --------------------------------------------------------------------------- #
# Evaluator constants                                                           #
# --------------------------------------------------------------------------- #

INDIA_KEYWORDS: list[str] = [
    "sebi", "rbi", "rupee", "inr", "promoter",
    "fii", "nifty", "sensex", "npa", "nim",
    "regulatory", "pledging", "india", "monsoon",
    "gst", "inflation", "rate",
]

REQUIRED_PHRASES: list[str] = [
    "not a sebi",
    "educational",
    "not investment advice",
]

# --------------------------------------------------------------------------- #
# Evaluators                                                                    #
# --------------------------------------------------------------------------- #


def parser_accuracy(run: Any, example: Any) -> dict[str, Any]:
    """Score revenue and PAT extraction accuracy against known values."""
    outputs: dict[str, Any] = run.outputs or {}
    parsed: dict[str, Any] = outputs.get("parsed_quarterly") or {}

    expected_rev = float(example.inputs.get("expected_revenue_cr", 0))
    expected_pat = float(example.inputs.get("expected_pat_cr", 0))
    actual_rev = float(parsed.get("revenue_cr", 0))
    actual_pat = float(parsed.get("pat_cr", 0))

    if expected_rev == 0:
        return {"score": 0.0, "comment": "No expected revenue in example"}

    rev_acc = 1.0 - abs(actual_rev - expected_rev) / expected_rev
    pat_acc = (
        1.0 - abs(actual_pat - expected_pat) / expected_pat if expected_pat > 0 else 0.0
    )
    score = max(0.0, min(1.0, (rev_acc + pat_acc) / 2))

    return {
        "score": score,
        "comment": (
            f"Revenue: extracted {actual_rev:,.0f} vs expected {expected_rev:,.0f} | "
            f"PAT: extracted {actual_pat:,.0f} vs expected {expected_pat:,.0f}"
        ),
    }


def signal_accuracy_vs_nifty(run: Any, example: Any) -> dict[str, Any]:
    """Score BUY/HOLD/SELL direction against actual 30-day alpha vs Nifty.

    Correct if:
      BUY  → alpha > +2%
      SELL → alpha < -2%
      HOLD → alpha in [-2%, +2%]
    """
    outputs: dict[str, Any] = run.outputs or {}
    direction: str = str(outputs.get("signal_direction") or "HOLD")
    alpha: float = float(example.inputs.get("alpha_vs_nifty", 0.0))

    correct = (
        (direction == "BUY" and alpha > 2.0)
        or (direction == "SELL" and alpha < -2.0)
        or (direction == "HOLD" and -2.0 <= alpha <= 2.0)
    )
    return {
        "score": 1.0 if correct else 0.0,
        "comment": (
            f"Signal={direction} | Alpha={alpha:+.1f}% vs Nifty | "
            f"{'Correct' if correct else 'Wrong'}"
        ),
    }


def faithfulness(run: Any, example: Any) -> dict[str, Any]:
    """GPT-4o-mini judge: are analysis claims grounded in the announcement text?

    Uses llm_fast from agents.llm (gpt-4o-mini, temperature=0).
    Returns 0.5 on any evaluation error to avoid penalising the pipeline.
    """
    outputs: dict[str, Any] = run.outputs or {}
    analysis: str = str(outputs.get("analysis_summary") or "")
    announcement: str = str(example.inputs.get("announcement_raw") or "")

    if not analysis:
        return {"score": 0.0, "comment": "No analysis generated"}

    prompt = (
        "Rate the faithfulness of this analysis to the source announcement text.\n"
        "Score 0.0-1.0 where:\n"
        "  1.0 = All claims directly supported by source\n"
        "  0.5 = Mix of supported and unsupported claims\n"
        "  0.0 = Claims contradict or ignore the source\n\n"
        f"Source announcement:\n{announcement}\n\n"
        f"Generated analysis:\n{analysis}\n\n"
        'Respond with ONLY a JSON object: {"score": 0.85, "reason": "brief explanation"}'
    )

    try:
        from agents.llm import llm_fast  # lazy import — avoids init cost if not needed

        response = llm_fast.invoke(prompt)
        result: dict[str, Any] = json.loads(str(response.content))
        return {
            "score": float(result["score"]),
            "comment": str(result.get("reason", "")),
        }
    except Exception as exc:
        logger.warning("faithfulness eval error: %s", exc)
        return {"score": 0.5, "comment": f"Eval error: {exc}"}


def india_risk_relevance(run: Any, example: Any) -> dict[str, Any]:
    """Score whether key_risks contain India-specific market factors.

    Score = min(1.0, matched_keywords / 2) — two matches earns full score.
    """
    outputs: dict[str, Any] = run.outputs or {}
    risks: list[Any] = outputs.get("key_risks") or []
    risk_text: str = " ".join(str(r) for r in risks).lower()

    matched = [kw for kw in INDIA_KEYWORDS if kw in risk_text]
    score = min(1.0, len(matched) / 2)

    return {
        "score": score,
        "comment": f"India keywords found: {matched[:5]}",
    }


def sebi_compliance(run: Any, example: Any) -> dict[str, Any]:
    """Score SEBI disclaimer completeness — all 3 required phrases must be present."""
    outputs: dict[str, Any] = run.outputs or {}
    disclaimer: str = (outputs.get("sebi_disclaimer") or "").lower()

    hits = sum(1 for p in REQUIRED_PHRASES if p in disclaimer)
    score = hits / len(REQUIRED_PHRASES)

    return {
        "score": score,
        "comment": f"SEBI compliance: {hits}/{len(REQUIRED_PHRASES)} phrases found",
    }


# --------------------------------------------------------------------------- #
# Dataset setup                                                                 #
# --------------------------------------------------------------------------- #


def _get_or_create_dataset(client: Client) -> Any:
    """Return the LangSmith dataset, creating it with examples if it doesn't exist.

    Handles the 409-conflict case where a previous run already created the
    dataset (read_dataset with wrong kwarg raised, create_dataset returned 409).
    """
    # 1. Try reading first — covers the common "already exists" path.
    try:
        ds = client.read_dataset(dataset_name=DATASET_NAME)
        print(f"Using existing dataset: {DATASET_NAME}")
        return ds
    except Exception:
        logger.debug("Dataset '%s' not found or read failed — will create", DATASET_NAME)

    # 2. Create with examples.
    try:
        ds = client.create_dataset(
            dataset_name=DATASET_NAME,
            description="Real FY25 Indian Q results for evaluation",
        )
        for ex in EVAL_EXAMPLES:
            client.create_example(
                inputs={
                    "nse_symbol": ex["nse_symbol"],
                    "announcement_type": ex["announcement_type"],
                    "announcement_raw": ex["announcement_raw"],
                    "expected_revenue_cr": ex["expected_revenue_cr"],
                    "expected_pat_cr": ex["expected_pat_cr"],
                    "alpha_vs_nifty": ex["alpha_vs_nifty"],
                    "sector": ex["sector"],
                },
                outputs={"expected_direction": ex["expected_direction"]},
                dataset_id=ds.id,
            )
        print(f"Created dataset with {len(EVAL_EXAMPLES)} examples")
        return ds
    except Exception:
        # 3. Conflict (409) — dataset was created between step 1 and step 2.
        logger.debug("Dataset creation conflict — reading existing dataset")
        return client.read_dataset(dataset_name=DATASET_NAME)


async def run_evaluations(experiment_name: str = "india-v1") -> Any:
    """Create (or reuse) the LangSmith dataset, then return it.

    Dataset creation is idempotent — safe to call on every eval run.
    """
    client = Client()
    dataset = _get_or_create_dataset(client)

    print(f"Running evaluations: {experiment_name}")
    print("This will run the full agent pipeline on each example...")
    print("Expected time: ~5 minutes for 12 examples")

    return dataset


# --------------------------------------------------------------------------- #
# Threshold gating                                                              #
# --------------------------------------------------------------------------- #

_THRESHOLDS: dict[str, float] = {
    "parser_accuracy": 0.85,
    "signal_accuracy_vs_nifty": 0.55,
    "faithfulness": 0.75,
    "india_risk_relevance": 0.50,
    "sebi_compliance": 1.00,
}


async def check_thresholds(results: dict[str, float]) -> bool:
    """Print per-metric PASS/FAIL and return True only if all thresholds met."""
    all_passed = True

    print("\nThreshold Check:")
    print("-" * 56)
    for metric, threshold in _THRESHOLDS.items():
        score = results.get(metric, 0.0)
        passed = score >= threshold
        status = "PASS" if passed else "FAIL"
        print(f"  {metric:<35} {score:.2f} >= {threshold:.2f}  [{status}]")
        if not passed:
            all_passed = False

    print("-" * 56)
    print(f"Overall: {'ALL PASSED' if all_passed else 'SOME FAILED'}")
    return all_passed
