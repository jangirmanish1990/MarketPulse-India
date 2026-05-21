"""Analysis router — trigger LangGraph pipeline and query results."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.auth import CurrentUser
from backend.config import IST, SEBI_DISCLAIMER, limiter, settings
from backend.database import get_db, get_session_factory
from backend.market_hours import (
    next_market_open,
    queue_announcement,
    should_process_now,
)
from backend.models import IndianStock, Signal
from backend.repositories import AnalysisSessionRepo, SignalRepo
from backend.stream_runner import run_graph_with_streaming

router = APIRouter()

DB = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class AnalyzeQueued(BaseModel):
    model_config = ConfigDict(frozen=True)

    session_id: str
    thread_id: str
    status: str
    nse_symbol: str
    ws_url: str
    message: str = ""


class SignalOut(BaseModel):
    model_config = ConfigDict(frozen=True)

    signal_id: str
    nse_symbol: str
    direction: str
    confidence: float
    current_price_inr: float | None
    target_price_inr: float | None
    upside_pct: float | None
    time_horizon_days: int | None
    rationale: str | None
    created_ist: str
    sebi_disclaimer: str


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------


def _build_initial_state(
    nse_symbol: str,
    session_id: str,
    thread_id: str,
    announcement_type: str = "quarterly_results",
    announcement_raw: str = "",
    exchange: str = "NSE",
) -> dict[str, Any]:
    return {
        "nse_symbol": nse_symbol,
        "bse_code": "",
        "exchange": exchange,
        "announcement_type": announcement_type,
        "announcement_raw": announcement_raw or f"Manual analysis triggered for {nse_symbol}",
        "s3_key": "",
        "thread_id": thread_id,
        "session_id": session_id,
        "sebi_disclaimer": SEBI_DISCLAIMER,
        "retry_count": 0,
        "node_timings": {},
        "price_history": {},
        "financials": {},
        "live_quote": {},
        "index_data": {},
        "usd_inr": 0.0,
        "parsed_quarterly": None,
        "parsed_board": None,
        "parsed_insider": None,
        "parsed_shp": None,
        "concall_available": False,
        "concall_tone": None,
        "concall_guidance_cr": None,
        "concall_signal_adjustment": None,
        "nifty_value": 0.0,
        "nifty_change_pct": 0.0,
        "sector_index_change_pct": 0.0,
        "fii_net_flow_cr": 0.0,
        "fii_sentiment": "neutral",
        "usd_inr_context": "stable",
        "market_status": "OPEN",
        "retrieved_docs": [],
        "doc_grades": [],
        "used_web_fallback": False,
        "promoter_pct": None,
        "promoter_trend": None,
        "promoter_pledging_pct": None,
        "promoter_pledging_risk": None,
        "fii_ownership_trend": None,
        "analysis_summary": None,
        "key_positives": None,
        "key_risks": None,
        "quarter_verdict": None,
        "sector_outlook": None,
        "signal_direction": None,
        "confidence": None,
        "current_price_inr": None,
        "target_price_inr": None,
        "upside_pct": None,
        "time_horizon_days": None,
        "rationale": None,
        "error": None,
    }


async def _run_graph_background(
    session_id: uuid.UUID,
    thread_id: str,
    nse_symbol: str,
    announcement_type: str = "quarterly_results",
    announcement_raw: str = "",
    exchange: str = "NSE",
) -> None:
    """Run the LangGraph pipeline (non-streaming) and update session status."""
    factory = get_session_factory()

    async with factory() as db:
        await AnalysisSessionRepo(db).update_status(thread_id, "running")
        await db.commit()

    state = _build_initial_state(
        nse_symbol, str(session_id), thread_id, announcement_type, announcement_raw, exchange
    )

    try:
        from agents.graph import build_graph  # lazy import

        graph = build_graph().compile()
        config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
        await graph.ainvoke(state, config=config)  # type: ignore[arg-type]

        async with factory() as db:
            await AnalysisSessionRepo(db).update_status(
                thread_id, "completed", completed_at=datetime.now(IST)
            )
            await db.commit()
    except Exception as exc:
        print(f"[analyze] Graph error for {nse_symbol} (thread {thread_id}): {exc}")
        async with factory() as db:
            await AnalysisSessionRepo(db).update_status(
                thread_id, "failed", completed_at=datetime.now(IST)
            )
            await db.commit()


async def _run_streaming_background(
    session_id: uuid.UUID,
    thread_id: str,
    nse_symbol: str,
    state: dict[str, Any],
) -> None:
    """Wrap run_graph_with_streaming with DB status bookkeeping."""
    factory = get_session_factory()

    async with factory() as db:
        await AnalysisSessionRepo(db).update_status(thread_id, "running")
        await db.commit()

    try:
        await run_graph_with_streaming(state, str(session_id), thread_id)

        async with factory() as db:
            await AnalysisSessionRepo(db).update_status(
                thread_id, "completed", completed_at=datetime.now(IST)
            )
            await db.commit()

    except Exception as exc:
        print(f"[analyze] Streaming error for {nse_symbol} (thread {thread_id}): {exc}")
        async with factory() as db:
            await AnalysisSessionRepo(db).update_status(
                thread_id, "failed", completed_at=datetime.now(IST)
            )
            await db.commit()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _signal_to_out(sig: Signal) -> SignalOut:
    return SignalOut(
        signal_id=str(sig.id),
        nse_symbol=sig.nse_symbol,
        direction=sig.direction,
        confidence=sig.confidence,
        current_price_inr=sig.current_price_inr,
        target_price_inr=sig.target_price_inr,
        upside_pct=sig.upside_pct,
        time_horizon_days=sig.time_horizon_days,
        rationale=sig.rationale,
        created_ist=sig.created_at.astimezone(IST).isoformat(),
        sebi_disclaimer=SEBI_DISCLAIMER,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/analyze/{nse_symbol}", response_model=AnalyzeQueued)
@limiter.limit(f"{settings.rate_limit_analyses_per_day}/day")  # type: ignore[misc]
async def trigger_analysis(
    request: Request,
    nse_symbol: str,
    background_tasks: BackgroundTasks,
    db: DB,
    current_user: CurrentUser,
) -> AnalyzeQueued:
    """Trigger a streaming pipeline run; return session_id + WebSocket URL."""
    nse_symbol = nse_symbol.upper()

    result = await db.execute(select(IndianStock).where(IndianStock.nse_symbol == nse_symbol))
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Symbol {nse_symbol} not found in the database.",
        )

    thread_id = f"api-{nse_symbol.lower()}-{uuid.uuid4().hex[:8]}"
    session = await AnalysisSessionRepo(db).create(
        thread_id=thread_id,
        nse_symbol=nse_symbol,
        trigger_type="api",
        started_at=datetime.now(IST),
        status="queued",
    )
    await db.commit()

    session_id = str(session.id)
    ws_url = f"ws://localhost:8000/ws/analyze/{session_id}"

    state = _build_initial_state(nse_symbol, session_id, thread_id)

    if not should_process_now():
        queue_announcement(
            {
                "nse_symbol": nse_symbol,
                "session_id": session_id,
                "thread_id": thread_id,
                "state": state,  # type: ignore[dict-item]
            }
        )
        return AnalyzeQueued(
            session_id=session_id,
            thread_id=thread_id,
            status="queued",
            nse_symbol=nse_symbol,
            ws_url=ws_url,
            message=(f"Market closed. Will process at {next_market_open().isoformat()}"),
        )

    background_tasks.add_task(
        _run_streaming_background,
        session.id,
        thread_id,
        nse_symbol,
        state,
    )

    return AnalyzeQueued(
        session_id=session_id,
        thread_id=thread_id,
        status="running",
        nse_symbol=nse_symbol,
        ws_url=ws_url,
        message=f"Analysis started for {nse_symbol}",
    )


@router.get("/analyze/{nse_symbol}/latest", response_model=SignalOut | None)
async def get_latest_signal(
    nse_symbol: str,
    db: DB,
    current_user: CurrentUser,
) -> SignalOut | None:
    """Return the most recent signal for an NSE symbol, or null if none exists."""
    signals = await SignalRepo(db).get_by_symbol(nse_symbol.upper(), limit=1)
    if not signals:
        return None
    return _signal_to_out(signals[0])
