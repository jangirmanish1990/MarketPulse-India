"""NSE announcement poller — AWS Lambda handler.

Invoked by EventBridge every 5 minutes on weekdays (09:00-16:00 IST).
For each active symbol in DynamoDB, fetches the latest NSE announcements,
compares against the stored last_seen_id, saves new filings to S3, and
POSTs each new announcement to the FastAPI webhook endpoint.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import boto3
import requests

IST = ZoneInfo("Asia/Kolkata")

logger = logging.getLogger(__name__)
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# --------------------------------------------------------------------------- #
# Environment                                                                   #
# --------------------------------------------------------------------------- #

FASTAPI_WEBHOOK_URL: str = os.environ["FASTAPI_WEBHOOK_URL"]
WEBHOOK_SECRET: str = os.environ["WEBHOOK_SECRET"]
POLL_STATE_TABLE: str = os.environ.get("NSE_POLL_STATE_TABLE", "nse-poll-state")
SYMBOLS_TABLE: str = os.environ.get("NSE_SYMBOLS_TABLE", "nse-watched-symbols")
S3_BUCKET: str = os.environ["S3_BUCKET"]
AWS_REGION: str = os.environ.get("AWS_DEFAULT_REGION", "ap-south-1")

# --------------------------------------------------------------------------- #
# AWS clients — initialised once per Lambda container                           #
# --------------------------------------------------------------------------- #

_dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
_s3 = boto3.client("s3", region_name=AWS_REGION)

# --------------------------------------------------------------------------- #
# NSE HTTP session                                                              #
# --------------------------------------------------------------------------- #

NSE_HOME = "https://www.nseindia.com"
_NSE_API = "https://www.nseindia.com/api"

_NSE_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.nseindia.com",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection": "keep-alive",
    "X-Requested-With": "XMLHttpRequest",
}

_nse_session: requests.Session | None = None
_last_nse_req: float = 0.0
_MIN_INTERVAL: float = 1.5  # seconds between NSE requests


def _build_nse_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(_NSE_HEADERS)
    try:
        s.get(NSE_HOME, timeout=10)
        time.sleep(1)
        logger.debug("NSE session established")
    except Exception:
        logger.warning("NSE homepage unreachable; proceeding without cookies")
    return s


def _nse_get(path: str) -> dict[str, Any] | list[Any]:
    """GET a path under the NSE API with rate-limiting and one cookie-refresh retry."""
    global _nse_session, _last_nse_req

    elapsed = time.monotonic() - _last_nse_req
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)

    if _nse_session is None:
        _nse_session = _build_nse_session()

    url = f"{_NSE_API}{path}"
    resp = _nse_session.get(url, timeout=12)
    _last_nse_req = time.monotonic()

    if resp.status_code in (401, 403):
        logger.info("NSE returned %d — rebuilding session and retrying", resp.status_code)
        _nse_session = _build_nse_session()
        time.sleep(1)
        resp = _nse_session.get(url, timeout=12)
        _last_nse_req = time.monotonic()

    resp.raise_for_status()
    return resp.json()  # type: ignore[no-any-return]


# --------------------------------------------------------------------------- #
# DynamoDB helpers                                                              #
# --------------------------------------------------------------------------- #


def _get_state(symbol: str) -> dict[str, Any]:
    table = _dynamodb.Table(POLL_STATE_TABLE)
    item: dict[str, Any] = table.get_item(Key={"nse_symbol": symbol}).get("Item", {})
    return item


def _put_state(symbol: str, last_id: str) -> None:
    table = _dynamodb.Table(POLL_STATE_TABLE)
    table.put_item(
        Item={
            "nse_symbol": symbol,
            "last_announcement_id": last_id,
            "last_polled_at": datetime.now(IST).isoformat(),
        }
    )


def _get_watched_symbols() -> list[str]:
    table = _dynamodb.Table(SYMBOLS_TABLE)
    resp = table.scan(
        FilterExpression="is_active = :t",
        ExpressionAttributeValues={":t": True},
    )
    return [str(item["nse_symbol"]) for item in resp.get("Items", [])]


# --------------------------------------------------------------------------- #
# S3 helpers                                                                    #
# --------------------------------------------------------------------------- #


def _s3_key(symbol: str, ann_id: str) -> str:
    today = datetime.now(IST).strftime("%Y/%m/%d")
    return f"announcements/{today}/{symbol}/{ann_id}.json"


def _save_to_s3(symbol: str, ann_id: str, payload: dict[str, Any]) -> str:
    key = _s3_key(symbol, ann_id)
    _s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=json.dumps(payload, ensure_ascii=False, default=str),
        ContentType="application/json",
        Tagging="Project=MarketPulse&Env=dev",
    )
    return key


# --------------------------------------------------------------------------- #
# Webhook caller                                                                #
# --------------------------------------------------------------------------- #


def _post_webhook(symbol: str, ann_type: str, ann_raw: str) -> bool:
    body = json.dumps(
        {
            "nse_symbol": symbol,
            "announcement_type": ann_type,
            "announcement_raw": ann_raw,
            "exchange": "NSE",
        }
    )
    try:
        resp = requests.post(
            FASTAPI_WEBHOOK_URL,
            data=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Secret": WEBHOOK_SECRET,
            },
            timeout=10,
        )
        if resp.status_code >= 400:
            logger.warning("Webhook returned HTTP %d for %s", resp.status_code, symbol)
            return False
        return True
    except Exception:
        logger.exception("Webhook POST failed for %s", symbol)
        return False


# --------------------------------------------------------------------------- #
# Announcement classification                                                   #
# --------------------------------------------------------------------------- #

_RESULTS_KEYWORDS = frozenset(
    ["quarterly result", "financial result", "q1", "q2", "q3", "q4", "annual result"]
)


def _classify(subject: str) -> str:
    low = subject.lower()
    if any(kw in low for kw in _RESULTS_KEYWORDS):
        return "quarterly_results"
    if "dividend" in low:
        return "dividend"
    if "buyback" in low:
        return "buyback"
    if "board meeting" in low:
        return "board_meeting"
    if "agm" in low or "egm" in low:
        return "agm_egm"
    return "general"


def _ann_id(ann: dict[str, Any]) -> str:
    """Return a stable string ID for an announcement."""
    if an_id := ann.get("an_id"):
        return str(an_id)
    raw = f"{ann.get('symbol','')}-{ann.get('desc','')}-{ann.get('exchdisstime','')}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]  # noqa: S324


# --------------------------------------------------------------------------- #
# Per-symbol poll                                                               #
# --------------------------------------------------------------------------- #


def _poll_symbol(symbol: str) -> int:
    """Poll one symbol; return number of new announcements dispatched."""
    logger.info("[%s] polling", symbol)
    try:
        data = _nse_get(
            f"/corp-info?index=equities&param=announcements&symbol={symbol}"
        )
    except Exception:
        logger.exception("[%s] NSE fetch failed", symbol)
        return 0

    announcements: list[dict[str, Any]] = (
        data if isinstance(data, list) else data.get("data", [])  # type: ignore[union-attr]
    )
    if not announcements:
        logger.info("[%s] no announcements returned", symbol)
        return 0

    state = _get_state(symbol)
    last_id = str(state.get("last_announcement_id", ""))

    # NSE returns newest first — collect until we hit the last-seen ID
    new_ids: list[str] = []
    new_anns: list[dict[str, Any]] = []
    for ann in announcements:
        aid = _ann_id(ann)
        if aid == last_id:
            break
        new_ids.append(aid)
        new_anns.append(ann)

    if not new_ids:
        logger.info("[%s] nothing new (last_id=%s)", symbol, last_id)
        return 0

    dispatched = 0
    for aid, ann in zip(new_ids, new_anns, strict=False):
        subject = str(ann.get("desc", ann.get("subject", "")))
        ann_type = _classify(subject)
        payload: dict[str, Any] = {
            "announcement_id": aid,
            "nse_symbol": symbol,
            "subject": subject,
            "type": ann_type,
            "exchange_time": ann.get("exchdisstime", ""),
            "raw": ann,
            "scraped_at": datetime.now(IST).isoformat(),
        }
        s3_key = _save_to_s3(symbol, aid, payload)
        logger.info("[%s] saved s3://%s/%s", symbol, S3_BUCKET, s3_key)

        if _post_webhook(symbol, ann_type, subject):
            dispatched += 1
            logger.info("[%s] webhook ok — id=%s type=%s", symbol, aid, ann_type)

    # newest ID is first; persist it as the new watermark
    _put_state(symbol, new_ids[0])
    logger.info("[%s] state updated last_id=%s", symbol, new_ids[0])
    return dispatched


# --------------------------------------------------------------------------- #
# Entry point                                                                   #
# --------------------------------------------------------------------------- #


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Lambda entry point — called by EventBridge every 5 min on weekdays."""
    start = datetime.now(IST)
    logger.info("NSE poller started at %s IST", start.isoformat())

    try:
        symbols = _get_watched_symbols()
    except Exception:
        logger.exception("Failed to read watched symbols from DynamoDB")
        return {"status": "error", "detail": "could not load symbols"}

    if not symbols:
        logger.warning("No active watched symbols — nothing to poll")
        return {"status": "ok", "symbols_polled": 0, "total_dispatched": 0}

    logger.info("Watching %d symbol(s): %s", len(symbols), symbols)

    total_dispatched = 0
    errors: list[str] = []
    for sym in symbols:
        try:
            total_dispatched += _poll_symbol(sym)
        except Exception:
            logger.exception("Unhandled error polling %s", sym)
            errors.append(sym)

    end = datetime.now(IST)
    elapsed_ms = int((end - start).total_seconds() * 1000)
    logger.info(
        "Done — polled=%d dispatched=%d errors=%d elapsed=%dms",
        len(symbols),
        total_dispatched,
        len(errors),
        elapsed_ms,
    )
    return {
        "status": "ok" if not errors else "partial",
        "symbols_polled": len(symbols),
        "total_dispatched": total_dispatched,
        "errors": errors,
        "elapsed_ms": elapsed_ms,
    }
