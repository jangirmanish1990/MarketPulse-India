"""Multi-channel alert dispatcher for MarketPulse India signals.

Single entry point for all outbound alert channels:
  - WhatsApp  — Meta Cloud API (aiohttp)
  - Telegram  — python-telegram-bot
  - SMS       — AWS SNS Direct SMS (boto3 + asyncio.to_thread)

All channels are optional and driven by environment variables; any
un-configured channel is silently skipped so the dispatcher never crashes
due to missing credentials.

Pass ``dry_run=True`` to preview the formatted messages without making any
network calls — useful for local development and tests.

Environment variables
---------------------
WHATSAPP_ACCESS_TOKEN       Meta System User access token
WHATSAPP_PHONE_NUMBER_ID    Meta WABA phone-number ID
WHATSAPP_TO_NUMBER          Recipient E.164 number  (+919876543210)
TELEGRAM_BOT_TOKEN          Telegram Bot API token
TELEGRAM_CHAT_ID            Target channel / chat ID (@mychannel or numeric)
ALERT_SMS_NUMBER            Recipient E.164 number  (+919876543210)
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Coroutine
from typing import Any

import aiohttp
import boto3  # type: ignore[import-untyped]
import telegram
from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "SIGNAL_EMOJI",
    "AlertPayload",
    "dispatch_alert",
    "format_sms",
    "format_telegram",
    "format_whatsapp",
    "send_sms",
    "send_telegram",
    "send_whatsapp",
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SIGNAL_EMOJI: dict[str, str] = {
    "BUY": "🟢",
    "HOLD": "🟡",
    "SELL": "🔴",
}

# SNS Transactional SMS hard limit (GSM-7 encoding); keep well under 160.
_SMS_MAX_CHARS: int = 160

# ---------------------------------------------------------------------------
# Payload model
# ---------------------------------------------------------------------------


class AlertPayload(BaseModel):
    """Immutable alert payload carrying all data needed to format every channel.

    ``frozen=True`` prevents accidental mutation after construction and makes
    instances safe to pass concurrently to multiple channel senders.
    """

    model_config = ConfigDict(frozen=True)

    nse_symbol: str
    company_name: str
    signal_direction: str = Field(
        description="BUY | HOLD | SELL",
        pattern="^(BUY|HOLD|SELL)$",
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Signal confidence 0–1")
    current_price_inr: float = Field(gt=0)
    target_price_inr: float = Field(gt=0)
    upside_pct: float = Field(description="Signed percentage vs current price")
    revenue_cr: float = Field(gt=0, description="Revenue in crores")
    pat_margin_pct: float = Field(description="PAT margin percentage")
    quarter: str = Field(description='e.g. "Q2 FY25"')
    key_positive: str = Field(description="Single best positive catalyst")
    key_risk: str = Field(description="Single biggest risk factor")
    triggered_by: str = Field(
        description='"announcement" | "morning_digest" | "pre_result"',
    )


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


def format_whatsapp(p: AlertPayload) -> str:
    """Return WhatsApp text body (Meta Cloud API, MarkdownV1 bold/italic)."""
    emoji = SIGNAL_EMOJI.get(p.signal_direction, "⚪")
    return (
        f"📊 *{p.nse_symbol} {p.quarter}*\n"
        f"₹{p.revenue_cr:,.0f} Cr revenue\n"
        f"\n"
        f"{emoji} *{p.signal_direction}* │ "
        f"Target ₹{p.target_price_inr:,.0f} "
        f"({p.upside_pct:+.1f}%)\n"
        f"Confidence: {p.confidence * 100:.0f}%\n"
        f"\n"
        f"✅ {p.key_positive}\n"
        f"⚠️ {p.key_risk}\n"
        f"\n"
        f"_Not SEBI registered. Educational only._"
    )


def format_telegram(p: AlertPayload) -> str:
    """Return Telegram HTML-formatted message (parse_mode='HTML')."""
    emoji = SIGNAL_EMOJI.get(p.signal_direction, "⚪")
    return (
        f"<b>📊 {p.nse_symbol} — {p.quarter}</b>\n"
        f"<i>{p.company_name}</i>\n"
        f"\n"
        f"{emoji} <b>{p.signal_direction}</b> │ "
        f"₹{p.current_price_inr:,.0f} → "
        f"₹{p.target_price_inr:,.0f} "
        f"({p.upside_pct:+.1f}%)\n"
        f"\n"
        f"Revenue: ₹{p.revenue_cr:,.0f} Cr\n"
        f"PAT Margin: {p.pat_margin_pct:.1f}%\n"
        f"Confidence: {p.confidence * 100:.0f}%\n"
        f"\n"
        f"✅ {p.key_positive}\n"
        f"⚠️ {p.key_risk}\n"
        f"\n"
        f"<i>⚠️ Not SEBI registered. Educational only.</i>"
    )


def format_sms(p: AlertPayload) -> str:
    """Return SMS body for AWS SNS Transactional delivery (≤160 chars).

    Raises:
        AssertionError: If the formatted text exceeds ``_SMS_MAX_CHARS``.
                        This is a programming invariant — callers must ensure
                        symbol / price values that fit the template.
    """
    emoji = SIGNAL_EMOJI.get(p.signal_direction, "⚪")
    text = (
        f"MarketPulse: {p.nse_symbol} {emoji}"
        f"{p.signal_direction} "
        f"Tgt Rs{p.target_price_inr:,.0f} "
        f"({p.upside_pct:+.1f}%) "
        f"Q:{p.confidence * 100:.0f}% "
        f"Not SEBI reg."
    )
    assert len(text) <= _SMS_MAX_CHARS, (  # noqa: S101
        f"SMS body is {len(text)} chars — exceeds the {_SMS_MAX_CHARS}-char GSM-7 limit. "
        "Shorten nse_symbol, reduce decimal places, or abbreviate further."
    )
    return text


# ---------------------------------------------------------------------------
# Channel senders
# ---------------------------------------------------------------------------


async def send_whatsapp(
    payload: AlertPayload,
    to_number: str,
    phone_number_id: str,
    access_token: str,
) -> bool:
    """Send a signal alert via the Meta Cloud API (WhatsApp Business Platform).

    Args:
        payload: Fully-populated alert data.
        to_number: Recipient phone in E.164 format (e.g. "+919876543210").
        phone_number_id: Meta WABA phone-number ID.
        access_token: Meta System User permanent access token.

    Returns:
        ``True`` if the API returned HTTP 200, ``False`` otherwise.
        Never raises — errors are printed and False is returned.
    """
    url = f"https://graph.facebook.com/v19.0/{phone_number_id}/messages"
    body: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "to": to_number.replace("+", ""),
        "type": "text",
        "text": {
            "body": format_whatsapp(payload),
            "preview_url": False,
        },
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=body, headers=headers) as resp:
            ok = resp.status == 200
            if not ok:
                error_text = await resp.text()
                print(f"[alerts] WhatsApp failed {resp.status}: {error_text}")
            return ok


async def send_telegram(
    payload: AlertPayload,
    bot_token: str,
    chat_id: str,
) -> bool:
    """Send a signal alert via the Telegram Bot API.

    Args:
        payload: Fully-populated alert data.
        bot_token: Telegram Bot API token (from @BotFather).
        chat_id: Target channel or chat — "@mychannel" or numeric ID.

    Returns:
        ``True`` on success, ``False`` on any exception.
        Never raises.
    """
    bot = telegram.Bot(token=bot_token)
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=format_telegram(payload),
            parse_mode="HTML",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[alerts] Telegram failed: {exc}")
        return False


async def send_sms(
    payload: AlertPayload,
    phone_number: str,
) -> bool:
    """Send a signal alert via AWS SNS Direct SMS (Transactional tier).

    The boto3 call is blocking; it is wrapped in ``asyncio.to_thread`` so the
    event loop is not blocked.

    Args:
        payload: Fully-populated alert data.
        phone_number: Recipient phone in E.164 format (e.g. "+919876543210").

    Returns:
        ``True`` if SNS returned a ``MessageId``, ``False`` on any exception.
        Never raises.
    """
    try:
        sns_client = boto3.client("sns", region_name="ap-south-1")
        resp: dict[str, Any] = await asyncio.to_thread(
            sns_client.publish,
            PhoneNumber=phone_number,
            Message=format_sms(payload),
            MessageAttributes={
                "AWS.SNS.SMS.SMSType": {
                    "DataType": "String",
                    "StringValue": "Transactional",
                },
                "AWS.SNS.SMS.SenderID": {
                    "DataType": "String",
                    "StringValue": "MRKTPLS",
                },
            },
        )
        return bool(resp.get("MessageId"))
    except Exception as exc:  # noqa: BLE001
        print(f"[alerts] SMS failed: {exc}")
        return False


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------


async def dispatch_alert(
    payload: AlertPayload,
    dry_run: bool = False,
) -> dict[str, bool]:
    """Fan the alert out to every configured channel concurrently.

    Configured channels are determined at call time by checking environment
    variables (see module docstring).  Any channel with missing credentials is
    skipped with a log line — it never causes an exception.

    The three channel senders are awaited via ``asyncio.gather`` so all HTTP /
    gRPC calls happen in parallel rather than sequentially.

    Args:
        payload: Fully-populated ``AlertPayload``.
        dry_run: When ``True``, print formatted previews for all three channels
                 and return ``{"whatsapp": True, "telegram": True, "sms": True,
                 "dry_run": True}`` without making any network calls.

    Returns:
        ``dict[str, bool]`` with keys ``"whatsapp"``, ``"telegram"``,
        ``"sms"``, and ``"dry_run"``.  Each channel key is ``True`` if the
        send succeeded (or was dry-run), ``False`` otherwise.
    """
    results: dict[str, bool] = {
        "whatsapp": False,
        "telegram": False,
        "sms": False,
        "dry_run": dry_run,
    }

    # ------------------------------------------------------------------
    # Dry-run: print previews and return early
    # ------------------------------------------------------------------
    if dry_run:
        print("\n--- WhatsApp Preview ---")
        print(format_whatsapp(payload))
        print("\n--- Telegram Preview ---")
        print(format_telegram(payload))
        print("\n--- SMS Preview ---")
        sms_text = format_sms(payload)
        print(sms_text)
        print(f"SMS length: {len(sms_text)} chars")
        results.update({"whatsapp": True, "telegram": True, "sms": True})
        return results

    # ------------------------------------------------------------------
    # Build per-channel coroutine list (only for configured channels)
    # ------------------------------------------------------------------
    tasks: list[tuple[str, Coroutine[Any, Any, bool]]] = []

    wa_token = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    wa_phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    wa_to = os.getenv("WHATSAPP_TO_NUMBER", "")
    if wa_token and wa_phone_id and wa_to:
        tasks.append(
            ("whatsapp", send_whatsapp(payload, wa_to, wa_phone_id, wa_token))
        )
    else:
        print("[alerts] WhatsApp not configured — skipping")

    tg_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    tg_chat = os.getenv("TELEGRAM_CHAT_ID", "")
    if tg_token and tg_chat:
        tasks.append(("telegram", send_telegram(payload, tg_token, tg_chat)))
    else:
        print("[alerts] Telegram not configured — skipping")

    sms_to = os.getenv("ALERT_SMS_NUMBER", "")
    if sms_to:
        tasks.append(("sms", send_sms(payload, sms_to)))
    else:
        print("[alerts] SMS not configured — skipping")

    # ------------------------------------------------------------------
    # Fire all configured channels concurrently
    # ------------------------------------------------------------------
    if tasks:
        gathered = await asyncio.gather(
            *[coro for _, coro in tasks],
            return_exceptions=True,
        )
        for (channel, _), outcome in zip(tasks, gathered):
            if isinstance(outcome, BaseException):
                print(f"[alerts] {channel} exception: {outcome}")
            else:
                results[channel] = bool(outcome)

    sent = sum(1 for k, v in results.items() if k != "dry_run" and v)
    print(f"[alerts] Dispatched to {sent}/3 channels")
    return results
