"""Async repository classes for MarketPulse India.

Each repo wraps an `AsyncSession` and exposes typed operations on a single
table. Repos do not commit on their own — the caller owns the transaction
boundary (FastAPI's `get_db` dependency hands out a session per request and
commits/rolls back on exit).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (
    AnalysisSession,
    Announcement,
    IndianStock,
    Signal,
    WatchlistItem,
)


# ---------------------------------------------------------------------------
class IndianStockRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        nse_symbol: str,
        company_name: str,
        bse_code: str | None = None,
        sector: str | None = None,
        market_cap_cr: float | None = None,
        is_nifty50: bool = False,
        is_sensex30: bool = False,
    ) -> IndianStock:
        stock = IndianStock(
            nse_symbol=nse_symbol,
            company_name=company_name,
            bse_code=bse_code,
            sector=sector,
            market_cap_cr=market_cap_cr,
            is_nifty50=is_nifty50,
            is_sensex30=is_sensex30,
        )
        self.session.add(stock)
        await self.session.flush()
        return stock

    async def get_by_nse_symbol(self, nse_symbol: str) -> IndianStock | None:
        stmt = select(IndianStock).where(IndianStock.nse_symbol == nse_symbol)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self) -> Sequence[IndianStock]:
        result = await self.session.execute(select(IndianStock).order_by(IndianStock.nse_symbol))
        return result.scalars().all()

    async def get_nifty50(self) -> Sequence[IndianStock]:
        result = await self.session.execute(
            select(IndianStock)
            .where(IndianStock.is_nifty50.is_(True))
            .order_by(IndianStock.nse_symbol)
        )
        return result.scalars().all()


# ---------------------------------------------------------------------------
class AnnouncementRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        nse_symbol: str,
        exchange: str,
        published_ist: datetime,
        announcement_type: str | None = None,
        raw_content: str | None = None,
        s3_key: str | None = None,
    ) -> Announcement:
        ann = Announcement(
            nse_symbol=nse_symbol,
            exchange=exchange,
            announcement_type=announcement_type,
            raw_content=raw_content,
            s3_key=s3_key,
            published_ist=published_ist,
        )
        self.session.add(ann)
        await self.session.flush()
        return ann

    async def get_unprocessed(self, *, limit: int = 100) -> Sequence[Announcement]:
        stmt = (
            select(Announcement)
            .where(Announcement.processed.is_(False))
            .order_by(Announcement.published_ist.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def mark_processed(self, announcement_id: uuid.UUID) -> bool:
        stmt = update(Announcement).where(Announcement.id == announcement_id).values(processed=True)
        result = cast("CursorResult[Any]", await self.session.execute(stmt))
        return (result.rowcount or 0) > 0


# ---------------------------------------------------------------------------
class AnalysisSessionRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        thread_id: str,
        nse_symbol: str,
        trigger_type: str | None = None,
        started_at: datetime | None = None,
        status: str = "pending",
    ) -> AnalysisSession:
        analysis = AnalysisSession(
            thread_id=thread_id,
            nse_symbol=nse_symbol,
            trigger_type=trigger_type,
            started_at=started_at,
            status=status,
        )
        self.session.add(analysis)
        await self.session.flush()
        return analysis

    async def get_by_thread_id(self, thread_id: str) -> AnalysisSession | None:
        stmt = select(AnalysisSession).where(AnalysisSession.thread_id == thread_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_status(
        self,
        thread_id: str,
        status: str,
        *,
        completed_at: datetime | None = None,
    ) -> bool:
        values: dict[str, Any] = {"status": status}
        if completed_at is not None:
            values["completed_at"] = completed_at
        stmt = (
            update(AnalysisSession).where(AnalysisSession.thread_id == thread_id).values(**values)
        )
        result = cast("CursorResult[Any]", await self.session.execute(stmt))
        return (result.rowcount or 0) > 0


# ---------------------------------------------------------------------------
class SignalRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        session_id: uuid.UUID,
        nse_symbol: str,
        direction: str,
        confidence: float,
        current_price_inr: float | None = None,
        target_price_inr: float | None = None,
        upside_pct: float | None = None,
        time_horizon_days: int | None = None,
        rationale: str | None = None,
    ) -> Signal:
        signal = Signal(
            session_id=session_id,
            nse_symbol=nse_symbol,
            direction=direction,
            confidence=confidence,
            current_price_inr=current_price_inr,
            target_price_inr=target_price_inr,
            upside_pct=upside_pct,
            time_horizon_days=time_horizon_days,
            rationale=rationale,
        )
        self.session.add(signal)
        await self.session.flush()
        return signal

    async def get_by_symbol(self, nse_symbol: str, *, limit: int = 50) -> Sequence[Signal]:
        stmt = (
            select(Signal)
            .where(Signal.nse_symbol == nse_symbol)
            .order_by(Signal.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_recent(self, limit: int = 20) -> Sequence[Signal]:
        stmt = select(Signal).order_by(Signal.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all()


# ---------------------------------------------------------------------------
class WatchlistRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(
        self,
        *,
        user_id: uuid.UUID,
        nse_symbol: str,
        alert_threshold: float = 0.75,
    ) -> WatchlistItem:
        item = WatchlistItem(
            user_id=user_id,
            nse_symbol=nse_symbol,
            alert_threshold=alert_threshold,
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def remove(self, *, user_id: uuid.UUID, nse_symbol: str) -> bool:
        stmt = select(WatchlistItem).where(
            WatchlistItem.user_id == user_id,
            WatchlistItem.nse_symbol == nse_symbol,
        )
        result = await self.session.execute(stmt)
        item = result.scalar_one_or_none()
        if item is None:
            return False
        await self.session.delete(item)
        return True

    async def get_by_user(self, user_id: uuid.UUID) -> Sequence[WatchlistItem]:
        stmt = (
            select(WatchlistItem)
            .where(WatchlistItem.user_id == user_id)
            .order_by(WatchlistItem.added_at.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()


__all__ = [
    "AnalysisSessionRepo",
    "AnnouncementRepo",
    "IndianStockRepo",
    "SignalRepo",
    "WatchlistRepo",
]
