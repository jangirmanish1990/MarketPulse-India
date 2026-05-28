"""Unit tests for backend/alerts/dispatcher.py.

All tests run offline (no network, no AWS, no Telegram/WhatsApp credentials).
External I/O is exercised only in dry_run mode or via mocks.
"""

from __future__ import annotations

import pytest

from backend.alerts.dispatcher import (
    SIGNAL_EMOJI,
    AlertPayload,
    dispatch_alert,
    format_sms,
    format_telegram,
    format_whatsapp,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_SAMPLE: dict[str, object] = {
    "nse_symbol": "RELIANCE",
    "company_name": "Reliance Industries Ltd",
    "signal_direction": "BUY",
    "confidence": 0.82,
    "current_price_inr": 2_950.0,
    "target_price_inr": 3_300.0,
    "upside_pct": 11.9,
    "revenue_cr": 232_000.0,
    "pat_margin_pct": 8.4,
    "quarter": "Q2 FY25",
    "key_positive": "Jio subscriber additions beat estimates",
    "key_risk": "O2C segment under margin pressure from weak PX spreads",
    "triggered_by": "announcement",
}


@pytest.fixture()
def payload() -> AlertPayload:
    return AlertPayload(**_SAMPLE)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# SIGNAL_EMOJI
# ---------------------------------------------------------------------------


def test_signal_emoji_keys() -> None:
    assert set(SIGNAL_EMOJI) == {"BUY", "HOLD", "SELL"}
    assert SIGNAL_EMOJI["BUY"] == "🟢"
    assert SIGNAL_EMOJI["HOLD"] == "🟡"
    assert SIGNAL_EMOJI["SELL"] == "🔴"


# ---------------------------------------------------------------------------
# AlertPayload validation
# ---------------------------------------------------------------------------


def test_payload_round_trip(payload: AlertPayload) -> None:
    assert payload.nse_symbol == "RELIANCE"
    assert payload.confidence == pytest.approx(0.82)
    assert payload.signal_direction == "BUY"


def test_payload_invalid_direction() -> None:
    with pytest.raises(Exception):  # noqa: B017
        AlertPayload(**{**_SAMPLE, "signal_direction": "STRONG_BUY"})  # type: ignore[arg-type]


def test_payload_confidence_out_of_range() -> None:
    with pytest.raises(Exception):  # noqa: B017
        AlertPayload(**{**_SAMPLE, "confidence": 1.5})  # type: ignore[arg-type]


def test_payload_frozen(payload: AlertPayload) -> None:
    """Pydantic frozen model must reject attribute mutation."""
    with pytest.raises(Exception):  # noqa: B017
        payload.nse_symbol = "TCS"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# format_whatsapp
# ---------------------------------------------------------------------------


def test_format_whatsapp_contains_symbol(payload: AlertPayload) -> None:
    msg = format_whatsapp(payload)
    assert "RELIANCE" in msg


def test_format_whatsapp_contains_emoji(payload: AlertPayload) -> None:
    msg = format_whatsapp(payload)
    assert "🟢" in msg


def test_format_whatsapp_contains_disclaimer(payload: AlertPayload) -> None:
    msg = format_whatsapp(payload)
    assert "Not SEBI registered" in msg


def test_format_whatsapp_contains_target(payload: AlertPayload) -> None:
    msg = format_whatsapp(payload)
    assert "3,300" in msg


def test_format_whatsapp_unknown_direction() -> None:
    p = AlertPayload(**{**_SAMPLE, "signal_direction": "HOLD"})  # type: ignore[arg-type]
    msg = format_whatsapp(p)
    assert "🟡" in msg


# ---------------------------------------------------------------------------
# format_telegram
# ---------------------------------------------------------------------------


def test_format_telegram_html_tags(payload: AlertPayload) -> None:
    msg = format_telegram(payload)
    assert "<b>" in msg
    assert "<i>" in msg


def test_format_telegram_contains_company(payload: AlertPayload) -> None:
    msg = format_telegram(payload)
    assert "Reliance Industries Ltd" in msg


def test_format_telegram_contains_pat_margin(payload: AlertPayload) -> None:
    msg = format_telegram(payload)
    assert "PAT Margin" in msg
    assert "8.4%" in msg


def test_format_telegram_sebi_disclaimer(payload: AlertPayload) -> None:
    msg = format_telegram(payload)
    assert "Not SEBI registered" in msg


def test_format_telegram_price_range(payload: AlertPayload) -> None:
    """Should show current → target price."""
    msg = format_telegram(payload)
    assert "2,950" in msg
    assert "3,300" in msg


# ---------------------------------------------------------------------------
# format_sms
# ---------------------------------------------------------------------------


def test_format_sms_under_160_chars(payload: AlertPayload) -> None:
    msg = format_sms(payload)
    assert len(msg) <= 160, f"SMS is {len(msg)} chars"


def test_format_sms_contains_symbol(payload: AlertPayload) -> None:
    assert "RELIANCE" in format_sms(payload)


def test_format_sms_contains_direction(payload: AlertPayload) -> None:
    assert "BUY" in format_sms(payload)


def test_format_sms_disclaimer(payload: AlertPayload) -> None:
    assert "Not SEBI reg" in format_sms(payload)


def test_format_sms_sell_direction() -> None:
    p = AlertPayload(**{**_SAMPLE, "signal_direction": "SELL", "upside_pct": -8.5})  # type: ignore[arg-type]
    msg = format_sms(p)
    assert "SELL" in msg
    assert len(msg) <= 160


def test_format_sms_assert_fires_on_overflow() -> None:
    """Artificially long symbol (>101 chars) must trip the 160-char guard.

    The fixed parts of the SMS template consume ~59 chars, so the symbol
    needs to exceed 101 chars to push the total past the 160-char limit.
    """
    long_sym = "A" * 110  # 110 + ~59 fixed = ~169 chars → over limit
    with pytest.raises(AssertionError, match="chars"):
        p = AlertPayload(**{**_SAMPLE, "nse_symbol": long_sym})  # type: ignore[arg-type]
        format_sms(p)


# ---------------------------------------------------------------------------
# dispatch_alert — dry_run (no credentials needed)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_dry_run_all_true(
    payload: AlertPayload,
    capsys: pytest.CaptureFixture[str],
) -> None:
    results = await dispatch_alert(payload, dry_run=True)

    assert results["dry_run"] is True
    assert results["whatsapp"] is True
    assert results["telegram"] is True
    assert results["sms"] is True


@pytest.mark.asyncio
async def test_dispatch_dry_run_prints_previews(
    payload: AlertPayload,
    capsys: pytest.CaptureFixture[str],
) -> None:
    await dispatch_alert(payload, dry_run=True)
    captured = capsys.readouterr()
    assert "WhatsApp Preview" in captured.out
    assert "Telegram Preview" in captured.out
    assert "SMS Preview" in captured.out
    assert "SMS length:" in captured.out


@pytest.mark.asyncio
async def test_dispatch_no_credentials_returns_false(
    payload: AlertPayload,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With all env vars unset, every channel should be skipped → False."""
    for var in (
        "WHATSAPP_ACCESS_TOKEN",
        "WHATSAPP_PHONE_NUMBER_ID",
        "WHATSAPP_TO_NUMBER",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
        "ALERT_SMS_NUMBER",
    ):
        monkeypatch.delenv(var, raising=False)

    results = await dispatch_alert(payload, dry_run=False)
    assert results["whatsapp"] is False
    assert results["telegram"] is False
    assert results["sms"] is False
    assert results["dry_run"] is False


@pytest.mark.asyncio
async def test_dispatch_keys_always_present(
    payload: AlertPayload,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Return dict must always contain all four keys regardless of config."""
    monkeypatch.delenv("WHATSAPP_ACCESS_TOKEN", raising=False)
    results = await dispatch_alert(payload, dry_run=False)
    assert {"whatsapp", "telegram", "sms", "dry_run"} == set(results.keys())


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_format_whatsapp_hold(payload: AlertPayload) -> None:
    p = AlertPayload(**{**_SAMPLE, "signal_direction": "HOLD"})  # type: ignore[arg-type]
    assert "🟡" in format_whatsapp(p)


def test_format_telegram_sell() -> None:
    p = AlertPayload(**{**_SAMPLE, "signal_direction": "SELL", "upside_pct": -5.0})  # type: ignore[arg-type]
    msg = format_telegram(p)
    assert "🔴" in msg
    assert "(-5.0%)" in msg


def test_format_whatsapp_upside_sign(payload: AlertPayload) -> None:
    """Upside percentage must carry a leading sign (+/-)."""
    msg = format_whatsapp(payload)
    assert "+11.9%" in msg
