"""LangSmith evaluators for MarketPulse India.

Each evaluator takes (run_output, example) and returns
{"key": str, "score": float, "comment": str}.
"""

from __future__ import annotations

import contextlib
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Evaluator 1 — Parser accuracy
# ---------------------------------------------------------------------------


def parser_accuracy(run_output: dict[str, Any], example: dict[str, Any]) -> dict[str, Any]:
    """Check whether parse_announcement extracted revenue and PAT within 5 percent."""
    parsed = run_output.get("parsed_quarterly") or {}
    exp_rev = float(example.get("expected_revenue_cr", 0) or 0)
    exp_pat = float(example.get("expected_pat_cr", 0) or 0)

    if not parsed or (not exp_rev and not exp_pat):
        return {"key": "parser_accuracy", "score": 0.0, "comment": "no parsed output"}

    def _pct_err(actual: float | None, expected: float) -> float:
        if actual is None or expected == 0:
            return 1.0
        return abs(actual - expected) / expected

    rev_actual: float | None = None
    pat_actual: float | None = None

    for key in ("revenue_cr", "net_revenue_cr", "total_revenue_cr", "revenue"):
        if key in parsed and parsed[key] is not None:
            with contextlib.suppress(TypeError, ValueError):
                rev_actual = float(parsed[key])
            break

    for key in ("net_profit_cr", "pat_cr", "profit_after_tax_cr", "net_profit"):
        if key in parsed and parsed[key] is not None:
            with contextlib.suppress(TypeError, ValueError):
                pat_actual = float(parsed[key])
            break

    checks: list[float] = []
    if exp_rev:
        checks.append(1.0 if _pct_err(rev_actual, exp_rev) <= 0.05 else 0.0)
    if exp_pat:
        checks.append(1.0 if _pct_err(pat_actual, exp_pat) <= 0.05 else 0.0)

    score = sum(checks) / len(checks) if checks else 0.0
    comment = f"rev={rev_actual} (exp {exp_rev}), pat={pat_actual} (exp {exp_pat})"
    return {"key": "parser_accuracy", "score": round(score, 4), "comment": comment}


# ---------------------------------------------------------------------------
# Evaluator 2 — Signal accuracy vs Nifty
# ---------------------------------------------------------------------------


def signal_accuracy_vs_nifty(run_output: dict[str, Any], example: dict[str, Any]) -> dict[str, Any]:
    """Score 1.0 if signal direction aligns with Nifty alpha vs expected."""
    signal = run_output.get("signal_direction")
    nifty_chg = float(example.get("nifty_1w_change_pct", 0) or 0)
    expected = example.get("expected_signal", "").upper()

    if not signal:
        return {"key": "signal_accuracy_vs_nifty", "score": 0.0, "comment": "no signal"}

    signal = str(signal).upper()
    if expected:
        score = 1.0 if signal == expected else 0.0
        return {
            "key": "signal_accuracy_vs_nifty",
            "score": score,
            "comment": f"got={signal} expected={expected}",
        }

    # fallback: score against Nifty alpha
    if nifty_chg > 2.0:
        correct = signal == "BUY"
    elif nifty_chg < -2.0:
        correct = signal == "SELL"
    else:
        correct = signal == "HOLD"

    return {
        "key": "signal_accuracy_vs_nifty",
        "score": 1.0 if correct else 0.0,
        "comment": f"got={signal} nifty_chg={nifty_chg:+.1f}",
    }


# ---------------------------------------------------------------------------
# Evaluator 3 — Faithfulness (LLM judge)
# ---------------------------------------------------------------------------

_FAITHFULNESS_PROMPT = """\
You are a financial analyst evaluating whether an AI-generated stock analysis \
is faithful to the source data.

SOURCE TEXT:
{announcement}

GENERATED ANALYSIS:
{analysis}

Score the faithfulness from 0.0 to 1.0:
- 1.0: All claims in the analysis are directly supported by the source text
- 0.5: Most claims are supported but some extrapolation exists
- 0.0: Analysis contains fabricated numbers or contradicts the source

Return ONLY valid JSON: {{"score": <float>, "reason": "<one sentence>"}}"""


def faithfulness(run_output: dict[str, Any], example: dict[str, Any]) -> dict[str, Any]:
    """LLM judge: is the generated analysis faithful to the source announcement?"""
    from agents.llm import llm_fast  # lazy import — agents not always available

    analysis = run_output.get("analysis_summary") or ""
    announcement = example.get("announcement_raw", "")

    if not analysis:
        return {"key": "faithfulness", "score": 0.0, "comment": "no analysis summary"}

    prompt = _FAITHFULNESS_PROMPT.format(announcement=announcement, analysis=analysis)
    try:
        response = llm_fast.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        data = json.loads(content)
        score = float(data.get("score", 0.0))
        reason = str(data.get("reason", ""))
    except Exception:
        logger.exception("[faithfulness] LLM judge failed")
        score, reason = 0.0, "judge error"

    return {"key": "faithfulness", "score": round(score, 4), "comment": reason}


# ---------------------------------------------------------------------------
# Evaluator 4 — India risk relevance
# ---------------------------------------------------------------------------

_INDIA_KEYWORDS = [
    "sebi",
    "rbi",
    "rupee",
    "inr",
    "promoter",
    "fii",
    "npa",
    "nim",
    "regulatory",
    "pledging",
    "india",
    "inflation",
    "rate",
    "monsoon",
    "gst",
    "currency",
]


def india_risk_relevance(run_output: dict[str, Any], example: dict[str, Any]) -> dict[str, Any]:
    """Check whether key_risks mentions India-specific risk factors."""
    risks = run_output.get("key_risks") or []
    if not risks:
        return {"key": "india_risk_relevance", "score": 0.0, "comment": "no key_risks"}

    risk_text = " ".join(str(r) for r in risks).lower()
    hits = sum(1 for kw in _INDIA_KEYWORDS if kw in risk_text)
    score = min(1.0, hits / 2)
    return {
        "key": "india_risk_relevance",
        "score": round(score, 4),
        "comment": f"{hits} India keywords found",
    }


# ---------------------------------------------------------------------------
# Evaluator 5 — SEBI compliance
# ---------------------------------------------------------------------------

_SEBI_PHRASES = [
    ("not a sebi", "not sebi"),
    ("educational",),
    ("not investment advice", "educational purposes"),
]


def sebi_compliance(run_output: dict[str, Any], example: dict[str, Any]) -> dict[str, Any]:
    """Verify all required SEBI disclaimer phrases are present (must be 1.0)."""
    disclaimer = str(run_output.get("sebi_disclaimer", "")).lower()
    missing: list[str] = []

    for phrase_group in _SEBI_PHRASES:
        if not any(p in disclaimer for p in phrase_group):
            missing.append(phrase_group[0])

    score = 1.0 if not missing else 0.0
    comment = "compliant" if not missing else f"missing: {missing}"
    return {"key": "sebi_compliance", "score": score, "comment": comment}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ALL_EVALUATORS = [
    parser_accuracy,
    signal_accuracy_vs_nifty,
    faithfulness,
    india_risk_relevance,
    sebi_compliance,
]

THRESHOLDS: dict[str, float] = {
    "parser_accuracy": 0.85,
    "signal_accuracy_vs_nifty": 0.50,
    "faithfulness": 0.75,
    "india_risk_relevance": 0.50,
    "sebi_compliance": 1.00,
}
