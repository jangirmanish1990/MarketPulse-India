"""NSE India session management.

NSE requires cookie-based authentication obtained by first visiting the
homepage. This module holds a module-level requests.Session that is
automatically refreshed whenever a request returns 401/403.

Rate limiting: enforces a minimum 1-second gap between requests to avoid
triggering NSE's anti-scraping measures.
"""

from __future__ import annotations

import logging
import time
from threading import Lock
from typing import Any

import requests

logger = logging.getLogger(__name__)

NSE_HOME = "https://www.nseindia.com"

_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.nseindia.com",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",  # omit br: requests lacks brotli support
    "Connection": "keep-alive",
    "X-Requested-With": "XMLHttpRequest",
}

_session: requests.Session | None = None
_session_lock: Lock = Lock()
_last_req_at: float = 0.0
_MIN_INTERVAL: float = 1.0


def _build_session() -> requests.Session:
    """Create a fresh requests.Session, seed cookies by hitting the homepage."""
    s = requests.Session()
    s.headers.update(_HEADERS)
    try:
        s.get(NSE_HOME, timeout=10)
        time.sleep(1)
        logger.debug("NSE session established")
    except Exception:
        logger.warning("NSE homepage unreachable; cookies may be missing")
    return s


def _get_session() -> requests.Session:
    global _session  # noqa: PLW0603
    with _session_lock:
        if _session is None:
            _session = _build_session()
        return _session


def nse_get(url: str) -> dict[str, Any]:
    """GET *url* from NSE API.

    Enforces 1-second rate limiting and transparently rebuilds the session
    on 401/403 responses, retrying once.
    """
    global _session, _last_req_at  # noqa: PLW0603

    elapsed = time.monotonic() - _last_req_at
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)

    session = _get_session()
    resp = session.get(url, timeout=10)
    _last_req_at = time.monotonic()

    if resp.status_code in (401, 403):
        logger.info("NSE returned %d — rebuilding session and retrying", resp.status_code)
        with _session_lock:
            _session = _build_session()
        time.sleep(1)
        resp = _session.get(url, timeout=10)
        _last_req_at = time.monotonic()

    resp.raise_for_status()

    body = resp.text.strip()
    if not body:
        raise ValueError(f"NSE returned empty body for {url!r} (status {resp.status_code})")
    if body.startswith("<"):
        raise ValueError(
            f"NSE returned HTML instead of JSON for {url!r} — "
            "session cookies may be stale or NSE is rate-limiting this IP"
        )

    try:
        result: dict[str, Any] = resp.json()
    except Exception as exc:
        preview = body[:300].replace("\n", " ")
        raise ValueError(
            f"NSE returned non-JSON for {url!r} — {exc} — body preview: {preview!r}"
        ) from exc
    return result
