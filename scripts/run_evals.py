"""Run the MarketPulse India LangSmith evaluation suite.

Creates (or reuses) the marketpulse-india-fy25 dataset on LangSmith, runs
parse + generate_analysis + score_signal on all 12 FY25 examples, scores them
with 5 evaluators, and prints a PASS/FAIL threshold table.

Usage:
    python scripts/run_evals.py

Required env vars (set in .env):
    OPENAI_API_KEY        — GPT-4o / GPT-4o-mini calls
    LANGCHAIN_API_KEY     — LangSmith dataset API
    DATABASE_URL          — Postgres (score_signal DB write, optional)

# Add to GitHub Actions:
# - name: Run LangSmith Evals
#   run: python scripts/run_evals.py
#   continue-on-error: true
#   env:
#     LANGCHAIN_API_KEY: ${{ secrets.LANGCHAIN_API_KEY }}
#     OPENAI_API_KEY:    ${{ secrets.OPENAI_API_KEY }}
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Windows: psycopg3 + asyncpg require SelectorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]

# Force UTF-8 on Windows cp1252 consoles so rupee symbol doesn't crash
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

logging.basicConfig(level=logging.WARNING, format="%(levelname)s  %(name)s  %(message)s")
logger = logging.getLogger(__name__)

SEP = "=" * 60


def _setup_dataset() -> None:
    """Create or verify the LangSmith dataset."""
    try:
        from langsmith import Client

        from tests.evals.langsmith_sync import create_dataset

        client = Client()
        create_dataset(client)
    except Exception:
        logger.warning("LangSmith dataset setup skipped (API unreachable or key missing)")


async def _run() -> bool:
    from tests.evals.runner import print_report, run_all_evaluations

    print(SEP)
    print("MarketPulse India — LangSmith Evaluation Suite")
    print("  Examples  : 12 FY25 Indian quarterly results")
    print("  Nodes     : parse_announcement + generate_analysis + score_signal")
    print(SEP)

    print("\nRunning evaluations...")
    outcome = await run_all_evaluations()
    avg_scores: dict[str, float] = outcome["avg_scores"]

    passed = print_report(avg_scores)
    return passed


def main() -> None:
    _setup_dataset()

    passed = asyncio.run(_run())
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
