"""Webhook router — receives external announcement events and triggers analysis."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import IST, settings
from backend.database import get_db
from backend.models import IndianStock
from backend.repositories import AnalysisSessionRepo
from backend.routers.analyze import _run_graph_background

router = APIRouter()

DB = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class AnnouncementBody(BaseModel):
    model_config = ConfigDict(frozen=True)

    nse_symbol: str
    announcement_type: str = "quarterly_results"
    announcement_raw: str = ""
    exchange: str = "NSE"


class WebhookReceived(BaseModel):
    model_config = ConfigDict(frozen=True)

    received: bool
    session_id: str
    nse_symbol: str


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/webhook/announcement", response_model=WebhookReceived)
async def receive_announcement(
    body: AnnouncementBody,
    background_tasks: BackgroundTasks,
    db: DB,
    x_webhook_secret: Annotated[str | None, Header()] = None,
) -> WebhookReceived:
    """Accept an external announcement and launch the full pipeline.

    Protected by the X-Webhook-Secret header.
    """
    if x_webhook_secret != settings.webhook_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Webhook-Secret header.",
        )

    nse_symbol = body.nse_symbol.upper()

    result = await db.execute(select(IndianStock).where(IndianStock.nse_symbol == nse_symbol))
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Symbol {nse_symbol} not found on NSE.",
        )

    thread_id = f"webhook-{nse_symbol.lower()}-{uuid.uuid4().hex[:8]}"
    session = await AnalysisSessionRepo(db).create(
        thread_id=thread_id,
        nse_symbol=nse_symbol,
        trigger_type="webhook",
        started_at=datetime.now(IST),
        status="queued",
    )
    await db.commit()

    background_tasks.add_task(
        _run_graph_background,
        session.id,
        thread_id,
        nse_symbol,
        body.announcement_type,
        body.announcement_raw,
        body.exchange,
    )

    return WebhookReceived(
        received=True,
        session_id=str(session.id),
        nse_symbol=nse_symbol,
    )
