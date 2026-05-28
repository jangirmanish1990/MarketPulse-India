"""Unit tests for the two scheduled-alert Lambda handlers.

All tests are fully offline:
  - DB calls are monkeypatched to return canned rows.
  - No real channel credentials are required (dry_run or mocked sends).
  - asyncio.run() / asyncio.to_thread() work normally in pytest-asyncio auto mode.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

# ---------------------------------------------------------------------------
# morning_digest
# ---------------------------------------------------------------------------
from lambdas.morning_digest.handler import (
    _is_dry_run as morning_is_dry_run,
    _psycopg_url as morning_psycopg_url,
    _quarter_label,
    _row_to_payload,
    _send_no_signals_notice,
    handler as morning_handler,
)

# ---------------------------------------------------------------------------
# pre_result_alert
# ---------------------------------------------------------------------------
from lambdas.pre_result_alert.handler import (
    TOMORROW_RESULTS_MOCK,
    _build_pre_result_text,
    _fetch_nse_calendar,
    _is_dry_run as pre_result_is_dry_run,
    _psycopg_url as pre_result_psycopg_url,
    _tomorrow_date_ist,
    handler as pre_result_handler,
)

IST = ZoneInfo("Asia/Kolkata")


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_signal_row(**kwargs: Any) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "nse_symbol": "RELIANCE",
        "direction": "BUY",
        "confidence": 0.85,
        "current_price_inr": 2950.0,
        "target_price_inr": 3300.0,
        "upside_pct": 11.9,
        "rationale": "Jio subscriber additions beat estimates",
        "created_at": datetime(2026, 5, 28, 14, 30, tzinfo=IST),
    }
    return {**defaults, **kwargs}


# ---------------------------------------------------------------------------
# _psycopg_url
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url_in, expected",
    [
        (
            "postgresql+asyncpg://user:pass@host/db",
            "postgresql://user:pass@host/db",
        ),
        (
            "postgresql+psycopg2://user:pass@host/db",
            "postgresql://user:pass@host/db",
        ),
        (
            "postgresql+psycopg://user:pass@host/db",
            "postgresql://user:pass@host/db",
        ),
        (
            "postgresql://user:pass@host/db",
            "postgresql://user:pass@host/db",
        ),
    ],
)
def test_psycopg_url_stripping(url_in: str, expected: str) -> None:
    assert morning_psycopg_url(url_in) == expected
    assert pre_result_psycopg_url(url_in) == expected


# ---------------------------------------------------------------------------
# _quarter_label
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "month, year, expected",
    [
        (5,  2026, "Q1 FY27"),   # May 2026 → Q1 of FY 2026-27
        (8,  2026, "Q2 FY27"),   # Aug 2026 → Q2
        (11, 2026, "Q3 FY27"),   # Nov 2026 → Q3
        (2,  2026, "Q4 FY26"),   # Feb 2026 → Q4 of FY 2025-26
        (4,  2025, "Q1 FY26"),   # Apr 2025 → start of FY 2025-26
        (3,  2027, "Q4 FY27"),   # Mar 2027 → last month of FY 2026-27
    ],
)
def test_quarter_label(month: int, year: int, expected: str) -> None:
    dt = datetime(year, month, 15, tzinfo=timezone.utc)
    assert _quarter_label(dt) == expected


# ---------------------------------------------------------------------------
# _row_to_payload
# ---------------------------------------------------------------------------


def test_row_to_payload_basic() -> None:
    row = _make_signal_row()
    p = _row_to_payload(row)
    assert p.nse_symbol == "RELIANCE"
    assert p.signal_direction == "BUY"
    assert p.confidence == pytest.approx(0.85)
    assert p.triggered_by == "morning_digest"
    assert p.current_price_inr == pytest.approx(2950.0)
    assert p.target_price_inr == pytest.approx(3300.0)
    assert p.quarter == "Q1 FY27"          # May 2026


def test_row_to_payload_null_prices_get_fallback() -> None:
    row = _make_signal_row(current_price_inr=None, target_price_inr=None, upside_pct=None)
    p = _row_to_payload(row)
    # gt=0 constraint must be satisfied
    assert p.current_price_inr > 0
    assert p.target_price_inr > 0
    assert p.upside_pct == pytest.approx(0.0)


def test_row_to_payload_revenue_placeholder() -> None:
    """revenue_cr is not in signals table — must use a gt=0 placeholder."""
    row = _make_signal_row()
    p = _row_to_payload(row)
    assert p.revenue_cr > 0


def test_row_to_payload_bad_direction_normalised_to_hold() -> None:
    row = _make_signal_row(direction="STRONG_BUY")
    p = _row_to_payload(row)
    assert p.signal_direction == "HOLD"


def test_row_to_payload_rationale_truncated() -> None:
    long_rationale = "A" * 200
    row = _make_signal_row(rationale=long_rationale)
    p = _row_to_payload(row)
    assert len(p.key_positive) <= 120


def test_row_to_payload_no_rationale_uses_fallback() -> None:
    row = _make_signal_row(rationale=None)
    p = _row_to_payload(row)
    assert "MarketPulse" in p.key_positive or len(p.key_positive) > 5


# ---------------------------------------------------------------------------
# _is_dry_run — morning
# ---------------------------------------------------------------------------


def test_morning_dry_run_explicit_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALERT_DRY_RUN", "true")
    assert morning_is_dry_run() is True


def test_morning_dry_run_explicit_false_with_dev_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALERT_DRY_RUN", "false")
    monkeypatch.setenv("ENV", "dev")
    # Explicit false beats ENV=dev
    assert morning_is_dry_run() is False


def test_morning_dry_run_env_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALERT_DRY_RUN", raising=False)
    monkeypatch.setenv("ENV", "prod")
    assert morning_is_dry_run() is False


def test_morning_dry_run_env_dev_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALERT_DRY_RUN", raising=False)
    monkeypatch.delenv("ENV", raising=False)
    # No vars set → default behaviour = dry (safety-first)
    assert morning_is_dry_run() is True


# ---------------------------------------------------------------------------
# morning_handler — integration (DB mocked)
# ---------------------------------------------------------------------------


def test_morning_handler_no_db_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    result = morning_handler({}, object())
    assert result["status"] == "error"
    assert "DATABASE_URL" in result["detail"]


def test_morning_handler_db_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("ALERT_DRY_RUN", "true")
    with patch(
        "lambdas.morning_digest.handler._fetch_signals",
        side_effect=Exception("connection refused"),
    ):
        result = morning_handler({}, object())
    assert result["status"] == "error"
    assert "connection refused" in result["detail"]


def test_morning_handler_no_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty DB → sends no-signals notice (via mocked Telegram)."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("ALERT_DRY_RUN", "true")
    with (
        patch("lambdas.morning_digest.handler._fetch_signals", return_value=[]),
        patch(
            "lambdas.morning_digest.handler._send_no_signals_notice",
            new_callable=AsyncMock,
        ) as mock_notice,
    ):
        result = morning_handler({}, object())

    assert result["status"] == "ok"
    assert result["alerts_sent"] == 0
    assert result["note"] == "no_signals_in_24h"
    mock_notice.assert_awaited_once()


def test_morning_handler_dry_run_with_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two signals in dry_run → both return success without real sends."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("ALERT_DRY_RUN", "true")

    rows = [
        _make_signal_row(nse_symbol="RELIANCE"),
        _make_signal_row(nse_symbol="TCS", direction="HOLD", confidence=0.72),
    ]

    with patch("lambdas.morning_digest.handler._fetch_signals", return_value=rows):
        result = morning_handler({}, object())

    assert result["status"] == "ok"
    assert result["alerts_sent"] == 2
    assert "RELIANCE" in result["symbols"]
    assert "TCS" in result["symbols"]
    assert result["dry_run"] is True


def test_morning_handler_bad_signal_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    """A row with an invalid direction is skipped; the valid row still sends."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("ALERT_DRY_RUN", "true")

    rows = [
        _make_signal_row(nse_symbol="INFY", direction="BUY"),
        _make_signal_row(nse_symbol="JUNK", confidence=2.5),  # confidence out of range
    ]

    with patch("lambdas.morning_digest.handler._fetch_signals", return_value=rows):
        result = morning_handler({}, object())

    # INFY should dispatch; JUNK's confidence=2.5 will fail AlertPayload validation
    assert result["status"] == "ok"
    assert "INFY" in result["symbols"]
    assert "JUNK" not in result["symbols"]


# ---------------------------------------------------------------------------
# _build_pre_result_text
# ---------------------------------------------------------------------------


def test_build_pre_result_text_with_signal() -> None:
    signal_row: dict[str, Any] = {"direction": "BUY", "current_price_inr": 1750.0}
    text = _build_pre_result_text("INFY", "Q Results", signal_row)
    assert "⏰ Results Tomorrow: INFY" in text
    assert "BUY @ ₹1,750" in text
    assert "Q Results" in text


def test_build_pre_result_text_no_signal() -> None:
    text = _build_pre_result_text("HDFCBANK", "Q Results", None)
    assert "⏰ Results Tomorrow: HDFCBANK" in text
    assert "No signal available" in text


def test_build_pre_result_text_no_price() -> None:
    signal_row: dict[str, Any] = {"direction": "SELL", "current_price_inr": None}
    text = _build_pre_result_text("WIPRO", "Q Results", signal_row)
    assert "SELL" in text
    assert "price unavailable" in text


# ---------------------------------------------------------------------------
# TOMORROW_RESULTS_MOCK
# ---------------------------------------------------------------------------


def test_mock_has_required_keys() -> None:
    for entry in TOMORROW_RESULTS_MOCK:
        assert "symbol" in entry
        assert "exchange" in entry
        assert "result_type" in entry


# ---------------------------------------------------------------------------
# _is_dry_run — pre_result
# ---------------------------------------------------------------------------


def test_pre_result_dry_run_explicit_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALERT_DRY_RUN", "true")
    assert pre_result_is_dry_run() is True


def test_pre_result_dry_run_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALERT_DRY_RUN", raising=False)
    monkeypatch.setenv("ENV", "prod")
    assert pre_result_is_dry_run() is False


# ---------------------------------------------------------------------------
# _tomorrow_date_ist
# ---------------------------------------------------------------------------


def test_tomorrow_date_ist_format() -> None:
    d = _tomorrow_date_ist()
    # Must be YYYY-MM-DD
    datetime.strptime(d, "%Y-%m-%d")


# ---------------------------------------------------------------------------
# _fetch_nse_calendar — fallback path
# ---------------------------------------------------------------------------


def test_fetch_nse_calendar_falls_back_on_network_error() -> None:
    tomorrow = _tomorrow_date_ist()
    with patch("requests.Session.get", side_effect=OSError("no network")):
        result = _fetch_nse_calendar(tomorrow)
    # Must fall back to mock, never raise
    assert result == TOMORROW_RESULTS_MOCK


def test_fetch_nse_calendar_falls_back_on_bad_json() -> None:
    tomorrow = _tomorrow_date_ist()
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(side_effect=ValueError("not json"))
    with patch("requests.Session.get", return_value=mock_resp):
        result = _fetch_nse_calendar(tomorrow)
    assert result == TOMORROW_RESULTS_MOCK


# ---------------------------------------------------------------------------
# pre_result_handler — integration (DB + network mocked)
# ---------------------------------------------------------------------------


def test_pre_result_handler_no_db_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    result = pre_result_handler({}, object())
    assert result["status"] == "error"
    assert "DATABASE_URL" in result["detail"]


def test_pre_result_handler_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both mock stocks alerted; no real network calls."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("ALERT_DRY_RUN", "true")

    def fake_fetch_signal(db_url: str, symbol: str) -> dict[str, Any] | None:
        if symbol == "INFY":
            return {"direction": "BUY", "current_price_inr": 1750.0}
        return None

    with (
        patch(
            "lambdas.pre_result_alert.handler._fetch_nse_calendar",
            return_value=list(TOMORROW_RESULTS_MOCK),
        ),
        patch(
            "lambdas.pre_result_alert.handler._fetch_latest_signal",
            side_effect=fake_fetch_signal,
        ),
    ):
        result = pre_result_handler({}, object())

    assert result["status"] == "ok"
    assert "INFY" in result["symbols_alerted"]
    assert "HDFCBANK" in result["symbols_alerted"]
    assert result["dry_run"] is True


def test_pre_result_handler_db_failure_for_one_symbol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DB failure for one symbol must not prevent alerting the other."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("ALERT_DRY_RUN", "true")

    call_count = 0

    def flaky_fetch_signal(db_url: str, symbol: str) -> dict[str, Any] | None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("DB timeout")
        return {"direction": "HOLD", "current_price_inr": 1600.0}

    with (
        patch(
            "lambdas.pre_result_alert.handler._fetch_nse_calendar",
            return_value=list(TOMORROW_RESULTS_MOCK),
        ),
        patch(
            "lambdas.pre_result_alert.handler._fetch_latest_signal",
            side_effect=flaky_fetch_signal,
        ),
    ):
        result = pre_result_handler({}, object())

    # Both should still appear (DB failure is gracefully handled → signal=None)
    assert result["status"] == "ok"
    assert len(result["symbols_alerted"]) == 2


def test_pre_result_handler_empty_calendar(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("ALERT_DRY_RUN", "true")

    with patch(
        "lambdas.pre_result_alert.handler._fetch_nse_calendar",
        return_value=[],
    ):
        result = pre_result_handler({}, object())

    assert result["status"] == "ok"
    assert result["symbols_alerted"] == []
