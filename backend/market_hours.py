"""Market hours helpers and in-memory announcement queue for MarketPulse India."""

from __future__ import annotations

from datetime import datetime, timedelta
from datetime import time as dt_time
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

MARKET_OPEN = dt_time(9, 15)
MARKET_CLOSE = dt_time(15, 30)
POST_MARKET_END = dt_time(16, 0)
PRE_MARKET_START = dt_time(7, 0)


def get_market_status() -> str:
    """Return NSE market status string based on current IST time."""
    now = datetime.now(IST)
    t = now.time()
    wd = now.weekday()
    if wd >= 5:
        return "WEEKEND"
    if t < PRE_MARKET_START:
        return "CLOSED"
    if t < MARKET_OPEN:
        return "PRE_MARKET"
    if t < MARKET_CLOSE:
        return "OPEN"
    if t < POST_MARKET_END:
        return "POST_MARKET"
    return "CLOSED"


def is_results_season() -> bool:
    """Return True if today falls inside a quarterly results window."""
    now = datetime.now(IST)
    m, d = now.month, now.day
    windows = [
        (1, 15, 2, 15),
        (4, 15, 5, 15),
        (7, 15, 8, 15),
        (10, 15, 11, 15),
    ]
    return any(m1 * 100 + d1 <= m * 100 + d <= m2 * 100 + d2 for m1, d1, m2, d2 in windows)


def next_market_open() -> datetime:
    """Return the next 9:15 AM IST on a weekday."""
    now = datetime.now(IST)
    candidate = now.replace(hour=9, minute=15, second=0, microsecond=0)
    if candidate <= now:
        candidate = candidate + timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate = candidate + timedelta(days=1)
    return candidate


def should_process_now() -> bool:
    """Return True if the market is in a state where we should run immediately."""
    return get_market_status() in ("OPEN", "PRE_MARKET", "POST_MARKET")


# In-memory queue for after-hours announcements
announcement_queue: list[dict[str, object]] = []


def queue_announcement(announcement: dict[str, object]) -> None:
    process_at = next_market_open()
    announcement["process_at_ist"] = process_at.isoformat()
    announcement_queue.append(announcement)
    print(f"[Queue] Announcement queued for {process_at.isoformat()}")


async def process_queued_announcements() -> list[dict[str, object]]:
    """Remove and return announcements whose process_at_ist has passed."""
    now = datetime.now(IST)
    ready = [
        a for a in announcement_queue if datetime.fromisoformat(str(a["process_at_ist"])) <= now
    ]
    for ann in ready:
        announcement_queue.remove(ann)
        print(f"[Queue] Processing queued announcement: {ann.get('nse_symbol')}")
    return ready


__all__ = [
    "announcement_queue",
    "get_market_status",
    "is_results_season",
    "next_market_open",
    "process_queued_announcements",
    "queue_announcement",
    "should_process_now",
]
