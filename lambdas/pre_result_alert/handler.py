"""Pre-Result Alert Lambda — fires at 6 AM IST (12:30 AM UTC) via EventBridge.

Workflow
--------
1. Fetch tomorrow's NSE results calendar (falls back to mock data if the NSE
   API is unavailable).
2. For each stock scheduled to report tomorrow, query the DB for the most
   recent MarketPulse signal (if any).
3. Send a compact pre-result alert text to all configured channels.
4. Return the list of symbols alerted.

Pre-result message format
-------------------------
    ⏰ Results Tomorrow: {symbol}
    Last signal: {direction} @ ₹{price}  —or—  No signal available
    Watch for Q Results after market hours.

Environment variables
---------------------
DATABASE_URL            postgresql+asyncpg://... (async prefix is stripped here)
ENV                     dev | prod  — "dev" forces dry_run (default: dev)
ALERT_DRY_RUN           true | false — explicit override; takes precedence over ENV
WHATSAPP_ACCESS_TOKEN   }
WHATSAPP_PHONE_NUMBER_ID} see backend/alerts/dispatcher.py
WHATSAPP_TO_NUMBER      }
TELEGRAM_BOT_TOKEN      }
TELEGRAM_CHAT_ID        }
LOG_LEVEL               INFO | DEBUG | WARNING  (default: INFO)

Local testing
-------------
    python -m lambdas.pre_result_alert.handler            # dry-run (safe default)
    python -m lambdas.pre_result_alert.handler --live     # real send (needs creds)
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Repo root on sys.path — allows direct local execution.
# In Lambda, backend/ is bundled into /var/task; this is a no-op.
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import aiohttp  # noqa: E402
import psycopg  # noqa: E402 — psycopg3 sync API; bundled as psycopg[binary]
import telegram  # noqa: E402 — python-telegram-bot
from psycopg.rows import dict_row  # noqa: E402

# Import dispatch_alert even though the pre-result format bypasses AlertPayload —
# the dispatcher module is the central hub for channel credentials and config.
from backend.alerts.dispatcher import dispatch_alert  # noqa: E402, F401

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

IST = ZoneInfo("Asia/Kolkata")

logger = logging.getLogger(__name__)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO"))

# Mock data used when the NSE results calendar API is unavailable.
# Symbol / exchange / result_type follow the NSE API's field naming.
TOMORROW_RESULTS_MOCK: list[dict[str, str]] = [
    {"symbol": "INFY",     "exchange": "NSE", "result_type": "Q Results"},
    {"symbol": "HDFCBANK", "exchange": "NSE", "result_type": "Q Results"},
]

_NSE_CALENDAR_URL = "https://www.nseindia.com/api/event-calendar"
_NSE_HOME = "https://www.nseindia.com"
_NSE_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.nseindia.com",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# Latest-signal query for a single symbol
_LATEST_SIGNAL_QUERY = """
SELECT
    direction,
    confidence,
    current_price_inr,
    created_at
FROM signals
WHERE nse_symbol = %s
ORDER BY created_at DESC
LIMIT 1
"""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_dry_run() -> bool:
    """Return True when no real alerts should be sent.

    Priority order:
    1. ``ALERT_DRY_RUN=true/false`` — explicit override
    2. ``ENV != prod`` — anything except "prod" is treated as dry
    """
    explicit = os.getenv("ALERT_DRY_RUN", "").strip().lower()
    if explicit in ("true", "1", "yes"):
        return True
    if explicit in ("false", "0", "no"):
        return False
    return os.getenv("ENV", "dev").lower() != "prod"


def _psycopg_url(db_url: str) -> str:
    """Strip the SQLAlchemy driver prefix so psycopg3 can parse the URL."""
    return (
        db_url.replace("postgresql+asyncpg://", "postgresql://")
        .replace("postgresql+psycopg2://", "postgresql://")
        .replace("postgresql+psycopg://", "postgresql://")
    )


def _tomorrow_date_ist() -> str:
    """Return tomorrow's date in IST as an ISO string (YYYY-MM-DD)."""
    return (datetime.now(IST) + timedelta(days=1)).strftime("%Y-%m-%d")


def _fetch_nse_calendar(tomorrow: str) -> list[dict[str, str]]:
    """Fetch tomorrow's results from the NSE events calendar.

    Returns a list of ``{"symbol": ..., "exchange": ..., "result_type": ...}``
    dicts.  Falls back to ``TOMORROW_RESULTS_MOCK`` on any failure so the
    Lambda never dies due to NSE rate-limiting or network issues.

    The NSE ``event-calendar`` API returns rows like::

        {"symbol": "INFY", "date": "15-Oct-2025", "purpose": "Quarterly Results", ...}
    """
    import requests  # bundled in project deps; lazy import keeps Lambda startup fast

    try:
        session = requests.Session()
        session.headers.update(_NSE_HEADERS)
        # Warm up NSE session (sets cookies)
        session.get(_NSE_HOME, timeout=8)

        resp = session.get(
            _NSE_CALENDAR_URL,
            params={"index": "equities"},
            timeout=12,
        )
        resp.raise_for_status()
        data: list[dict[str, Any]] = resp.json()

        results: list[dict[str, str]] = []
        for item in data:
            # NSE date formats vary; try both "DD-MMM-YYYY" and "YYYY-MM-DD"
            raw_date: str = str(item.get("date", ""))
            item_date: str = ""
            for fmt in ("%d-%b-%Y", "%Y-%m-%d"):
                try:
                    item_date = datetime.strptime(raw_date, fmt).strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue

            if item_date != tomorrow:
                continue

            purpose = str(item.get("purpose", "")).lower()
            if "result" not in purpose:
                continue

            results.append({
                "symbol": str(item.get("symbol", "")),
                "exchange": "NSE",
                "result_type": str(item.get("purpose", "Q Results")),
            })

        if results:
            logger.info(
                "[pre_result] NSE calendar: %d result(s) for %s", len(results), tomorrow
            )
            return results

        logger.info("[pre_result] NSE calendar returned 0 results for %s — using mock", tomorrow)

    except Exception as exc:  # noqa: BLE001
        logger.warning("[pre_result] NSE calendar fetch failed (%s) — using mock data", exc)

    return list(TOMORROW_RESULTS_MOCK)


def _fetch_latest_signal(
    db_url: str, symbol: str
) -> dict[str, Any] | None:
    """Return the most recent DB signal for *symbol*, or None if absent."""
    conn_url = _psycopg_url(db_url)
    with psycopg.connect(conn_url, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(_LATEST_SIGNAL_QUERY, (symbol,))
            return cur.fetchone()  # type: ignore[return-value]


def _build_pre_result_text(
    symbol: str,
    result_type: str,
    signal_row: dict[str, Any] | None,
) -> str:
    """Return the pre-result alert text for one stock.

    Format::

        ⏰ Results Tomorrow: INFY
        Last signal: BUY @ ₹1,250
        Watch for Q Results after market hours.

    When no DB signal exists the second line reads "No signal available".
    """
    if signal_row is not None:
        direction = str(signal_row.get("direction", "HOLD")).upper()
        price_raw = signal_row.get("current_price_inr")
        if price_raw is not None:
            signal_line = f"Last signal: {direction} @ ₹{float(price_raw):,.0f}"
        else:
            signal_line = f"Last signal: {direction} (price unavailable)"
    else:
        signal_line = "Last signal: No signal available"

    return (
        f"⏰ Results Tomorrow: {symbol}\n"
        f"{signal_line}\n"
        f"Watch for {result_type} after market hours."
    )


# ---------------------------------------------------------------------------
# Async channel sends
# ---------------------------------------------------------------------------


async def _send_text_telegram(text: str, dry_run: bool) -> bool:
    """Send raw text to the configured Telegram channel.

    Returns True on success, False otherwise.  Never raises.
    """
    if dry_run:
        return True  # preview handled by caller

    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.getenv("TELEGRAM_CHAT_ID", "")
    if not (tg_token and tg_chat):
        logger.info("[pre_result] Telegram not configured — skipping")
        return False

    bot = telegram.Bot(token=tg_token)
    try:
        await bot.send_message(chat_id=tg_chat, text=text)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("[pre_result] Telegram send failed: %s", exc)
        return False


async def _send_text_whatsapp(text: str, dry_run: bool) -> bool:
    """Send raw text to the configured WhatsApp number via Meta Cloud API.

    Returns True on HTTP 200, False otherwise.  Never raises.
    """
    if dry_run:
        return True  # preview handled by caller

    wa_token = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    wa_phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    wa_to = os.getenv("WHATSAPP_TO_NUMBER", "")
    if not (wa_token and wa_phone_id and wa_to):
        logger.info("[pre_result] WhatsApp not configured — skipping")
        return False

    url = f"https://graph.facebook.com/v19.0/{wa_phone_id}/messages"
    body: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": wa_to.replace("+", ""),
        "type": "text",
        "text": {"body": text, "preview_url": False},
    }
    headers = {
        "Authorization": f"Bearer {wa_token}",
        "Content-Type": "application/json",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=body, headers=headers) as resp:
                ok = resp.status == 200
                if not ok:
                    err = await resp.text()
                    logger.warning("[pre_result] WhatsApp returned %d: %s", resp.status, err)
                return ok
    except Exception as exc:  # noqa: BLE001
        logger.warning("[pre_result] WhatsApp send failed: %s", exc)
        return False


async def _send_pre_result_alert(
    symbol: str,
    result_type: str,
    signal_row: dict[str, Any] | None,
    dry_run: bool,
) -> dict[str, bool]:
    """Build message text and fan it out to Telegram + WhatsApp concurrently.

    SMS is intentionally omitted — the message can exceed 160 chars when
    stacked with the symbol and price, and pre-result info is low-urgency.

    Returns a channel-result dict: ``{"telegram": bool, "whatsapp": bool}``.
    """
    text = _build_pre_result_text(symbol, result_type, signal_row)

    if dry_run:
        print(f"\n[pre_result] Preview for {symbol}:\n{text}\n")

    tg_result, wa_result = await asyncio.gather(
        _send_text_telegram(text, dry_run),
        _send_text_whatsapp(text, dry_run),
        return_exceptions=False,
    )

    return {"telegram": bool(tg_result), "whatsapp": bool(wa_result)}


# ---------------------------------------------------------------------------
# Top-level async orchestrator
# ---------------------------------------------------------------------------


async def _run(
    results_calendar: list[dict[str, str]],
    db_url: str,
    dry_run: bool,
) -> list[str]:
    """Process every stock in *results_calendar* concurrently.

    For each stock:
    1. Fetch the latest DB signal (sync — wrapped in ``asyncio.to_thread`` to
       avoid blocking the event loop).
    2. Send the pre-result alert to all configured channels.

    Returns the list of symbols that were successfully alerted.
    """
    async def _process_one(entry: dict[str, str]) -> str | None:
        symbol = entry["symbol"]
        result_type = entry.get("result_type", "Q Results")

        try:
            signal_row: dict[str, Any] | None = await asyncio.to_thread(
                _fetch_latest_signal, db_url, symbol
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[pre_result] DB lookup failed for %s: %s — proceeding anyway", symbol, exc)
            signal_row = None

        channel_results = await _send_pre_result_alert(symbol, result_type, signal_row, dry_run)
        any_sent = any(channel_results.values())

        if any_sent or dry_run:
            logger.info(
                "[pre_result] ✓ %s | signal=%s | channels=%s",
                symbol,
                "yes" if signal_row else "no",
                channel_results,
            )
            return symbol

        logger.warning("[pre_result] ✗ %s — no channel confirmed delivery", symbol)
        return None

    # Fire all stocks concurrently
    outcomes = await asyncio.gather(*[_process_one(e) for e in results_calendar])
    return [sym for sym in outcomes if sym is not None]


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------


def handler(event: dict[str, Any], context: object) -> dict[str, Any]:
    """Lambda entry point — called by EventBridge at 06:00 IST (00:30 UTC).

    Args:
        event:   EventBridge scheduled event dict (ignored).
        context: Lambda context object (ignored).

    Returns:
        Summary dict with the list of alerted symbols.
    """
    start = datetime.now(IST)
    dry_run = _is_dry_run()
    tomorrow = _tomorrow_date_ist()

    logger.info(
        "[pre_result] started | ts=%s | tomorrow=%s | dry_run=%s",
        start.strftime("%Y-%m-%d %H:%M:%S IST"),
        tomorrow,
        dry_run,
    )

    # ── 1. Validate env ──────────────────────────────────────────────────────
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        logger.error("[pre_result] DATABASE_URL is not set")
        return {"status": "error", "detail": "DATABASE_URL not set", "symbols_alerted": []}

    # ── 2. Fetch tomorrow's results calendar ─────────────────────────────────
    results_calendar = _fetch_nse_calendar(tomorrow)
    logger.info(
        "[pre_result] calendar: %d stock(s) reporting on %s → %s",
        len(results_calendar),
        tomorrow,
        [e["symbol"] for e in results_calendar],
    )

    if not results_calendar:
        print(f"[pre_result] No stocks reporting on {tomorrow} — nothing to alert")
        return {
            "status": "ok",
            "symbols_alerted": [],
            "tomorrow": tomorrow,
            "dry_run": dry_run,
        }

    # ── 3. Dispatch alerts (one event loop for all async work) ───────────────
    symbols_alerted = asyncio.run(_run(results_calendar, db_url, dry_run))

    # ── 4. Print execution summary ───────────────────────────────────────────
    elapsed_ms = int((datetime.now(IST) - start).total_seconds() * 1000)
    print(
        f"[pre_result] DONE | "
        f"calendar={[e['symbol'] for e in results_calendar]} | "
        f"alerted={symbols_alerted} | "
        f"dry_run={dry_run} | "
        f"elapsed={elapsed_ms}ms"
    )
    return {
        "status": "ok",
        "symbols_alerted": symbols_alerted,
        "tomorrow": tomorrow,
        "dry_run": dry_run,
        "elapsed_ms": elapsed_ms,
    }


# ---------------------------------------------------------------------------
# Local testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    import json

    from dotenv import load_dotenv  # type: ignore[import-not-found]

    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Pre-Result Alert Lambda — local test runner"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Actually send alerts (requires real credentials in .env). "
             "Without this flag, dry_run=True is forced regardless of .env.",
    )
    args = parser.parse_args()

    if not args.live:
        os.environ["ALERT_DRY_RUN"] = "true"
        print("[pre_result] Running in DRY-RUN mode (pass --live to send for real)\n")
    else:
        print("[pre_result] Running in LIVE mode — alerts will be sent!\n")

    result = handler({}, object())
    print(f"\n{'─' * 50}")
    print(json.dumps(result, indent=2, default=str))
