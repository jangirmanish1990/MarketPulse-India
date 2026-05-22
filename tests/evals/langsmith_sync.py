"""Sync helpers for LangSmith dataset management.

Uses list_datasets() to check existence before create to avoid 409 conflicts.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from tests.evals.dataset import DATASET_NAME, EVAL_EXAMPLES

if TYPE_CHECKING:
    from langsmith import Client

logger = logging.getLogger(__name__)


def create_dataset(client: Client) -> Any:
    """Return the LangSmith dataset, creating it (and its examples) if absent."""
    existing = list(client.list_datasets(dataset_name=DATASET_NAME))
    if existing:
        ds = existing[0]
        logger.info("Reusing dataset '%s' (id=%s)", DATASET_NAME, ds.id)
        return ds

    ds = client.create_dataset(
        dataset_name=DATASET_NAME,
        description="MarketPulse India FY25 quarterly results — 12 examples",
    )
    logger.info("Created dataset '%s' (id=%s)", DATASET_NAME, ds.id)

    for ex in EVAL_EXAMPLES:
        inputs = {
            "nse_symbol": ex["nse_symbol"],
            "announcement_type": ex["announcement_type"],
            "announcement_raw": ex["announcement_raw"],
        }
        outputs = {
            "expected_revenue_cr": ex.get("expected_revenue_cr"),
            "expected_pat_cr": ex.get("expected_pat_cr"),
            "nifty_1w_change_pct": ex.get("nifty_1w_change_pct"),
            "expected_signal": ex.get("expected_signal"),
        }
        client.create_example(inputs=inputs, outputs=outputs, dataset_id=ds.id)

    logger.info("Seeded %d examples into dataset", len(EVAL_EXAMPLES))
    return ds
