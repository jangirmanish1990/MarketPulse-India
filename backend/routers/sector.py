"""Sector analysis router — POST /sector/analyze + GET /sector/rankings/{sector}.

Provides a clean body-based API for the sector comparison page:

  POST /api/sector/analyze        { "sector": "IT" }
  GET  /api/sector/rankings/{sector}

The POST endpoint fans out over all 5 constituent stocks in parallel using the
LangGraph Send API (agents/sector_graph.py), fetches yfinance fundamentals for
each peer, then ranks them by a composite fundamental score.

The GET endpoint returns HTTP 200 with an empty rankings list when no
persistent ranking cache exists.  Clients should call POST to generate
fresh rankings, then display them immediately from the POST response.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

# HTTPException is still used by analyze_sector below (404 on unknown sector / 504 timeout).
from sqlalchemy.ext.asyncio import AsyncSession

from agents.sector_graph import SECTOR_SYMBOLS, run_sector_analysis
from backend.auth import CurrentUser
from backend.config import SEBI_DISCLAIMER
from backend.database import get_db

router = APIRouter()

DB = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class SectorAnalyzeRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    sector: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/sector/rankings/{sector}")
async def get_sector_rankings(
    sector: str,
    current_user: CurrentUser,  # noqa: ARG001 — auth guard
) -> dict[str, Any]:
    """Return cached sector rankings.

    No persistent ranking cache is stored yet — returns an empty rankings
    list with HTTP 200 so clients (and load tests) can handle the response
    gracefully.  Call POST /api/sector/analyze to generate a fresh ranking
    set; the UI should call GET after receiving those results.
    """
    return {
        "sector": sector,
        "rankings": [],
        "total": 0,
        "cached": False,
        "message": (
            f"No cached rankings for '{sector}'. "
            "POST /api/sector/analyze to generate fresh results."
        ),
        "sebi_disclaimer": SEBI_DISCLAIMER,
    }


@router.post("/sector/analyze")
async def analyze_sector(
    body: SectorAnalyzeRequest,
    db: DB,  # noqa: ARG001 — kept for auth dependency chain + future DB writes
    current_user: CurrentUser,  # noqa: ARG001 — auth guard
) -> dict[str, Any]:
    """Run the live parallel sector-analysis graph.

    Request body
    ------------
    ``{"sector": "IT"}``

    Valid sectors: IT · Banking · FMCG · Pharma · Energy

    Response
    --------
    sector          — canonical sector key
    sector_signal   — "bullish" | "neutral" | "bearish"
    sector_winner   — NSE symbol of the top-ranked stock
    fii_trend       — FII flow direction
    sector_ranking  — list of PeerResult dicts sorted by rank
    total_analyzed  — stocks successfully analyzed (no error)
    sebi_disclaimer — mandatory disclaimer string
    """
    # ── Resolve sector (case-insensitive) ───────────────────────────────────
    sector_key: str | None = None
    for k in SECTOR_SYMBOLS:
        if k.lower() == body.sector.lower():
            sector_key = k
            break

    if sector_key is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown sector '{body.sector}'. "
                f"Valid options: {', '.join(sorted(SECTOR_SYMBOLS))}"
            ),
        )

    session_id = str(uuid.uuid4())
    result_container: dict[str, Any] = {}
    error_container: dict[str, str] = {}

    # ── Run sector graph in a dedicated thread with its own event loop ───────
    # FastAPI's event loop must not be blocked; the async LangGraph graph gets
    # its own loop so it runs cleanly on all platforms (incl. Windows).
    def _run() -> None:
        if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            data = loop.run_until_complete(
                run_sector_analysis(sector_key, session_id)  # type: ignore[arg-type]
            )
            result_container["data"] = data
        except Exception as exc:
            error_container["error"] = str(exc)
        finally:
            loop.close()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=90)  # 90 s — 5 stocks × ~15 s each, with margin

    if thread.is_alive():
        raise HTTPException(status_code=504, detail="Sector analysis timed out")
    if "error" in error_container:
        raise HTTPException(status_code=500, detail=error_container["error"])

    graph_result: dict[str, Any] = result_container["data"]
    sector_ranking: list[dict[str, Any]] = [
        dict(p) for p in graph_result.get("sector_ranking", [])
    ]
    total_analyzed = sum(1 for p in sector_ranking if not p.get("error"))

    return {
        "sector": sector_key,
        "session_id": session_id,
        "sector_signal": graph_result.get("sector_signal", "neutral"),
        "sector_winner": graph_result.get("sector_winner", ""),
        "fii_trend": graph_result.get("fii_trend", "neutral"),
        "sector_ranking": sector_ranking,
        "total_analyzed": total_analyzed,
        "sebi_disclaimer": SEBI_DISCLAIMER,
    }
