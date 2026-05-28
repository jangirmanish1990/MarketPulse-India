"""scripts/test_alerts.py — end-to-end format + dispatch smoke test for alert channels.

Usage
-----
    uv run python scripts/test_alerts.py
    python scripts/test_alerts.py

What this tests
---------------
Uses a realistic INFY Q2 FY25 mock signal to validate four things:

  Test 1 — WhatsApp format preview
    • Renders format_whatsapp() and asserts key fields are present.
    • Checks SEBI disclaimer is embedded.

  Test 2 — Telegram format preview
    • Renders format_telegram() and asserts HTML tags + upside pct.

  Test 3 — SMS format + 160-char length guard
    • Renders format_sms() and asserts it is within the GSM-7 hard limit.

  Test 4 — Full dry_run dispatch
    • Calls dispatch_alert(dry_run=True) which exercises the entire
      dispatcher without making any real network calls.
    • Asserts all three channel flags are True in the result.

No credentials, no network, no DB required.

Windows SelectorEventLoop fix
------------------------------
Windows uses ProactorEventLoop by default. aiohttp (used by the WhatsApp
sender) requires SelectorEventLoop.  The fix is applied in main() exactly
as every other script in this repo does it:

    loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
    loop.run_until_complete(...)
    loop.close()
"""

from __future__ import annotations

import asyncio
import selectors
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Repo root on sys.path so the script works from any cwd.
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Windows: force UTF-8 so ₹ / emoji chars don't raise UnicodeEncodeError.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from backend.alerts.dispatcher import (  # noqa: E402
    AlertPayload,
    dispatch_alert,
    format_sms,
    format_telegram,
    format_whatsapp,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SEP  = "─" * 52
_THIN = "·" * 52

# ---------------------------------------------------------------------------
# Mock signal — realistic INFY Q2 FY25 announcement signal
# ---------------------------------------------------------------------------

MOCK_SIGNAL = AlertPayload(
    nse_symbol="INFY",
    company_name="Infosys Ltd",
    signal_direction="BUY",
    confidence=0.84,
    current_price_inr=1_847.50,
    target_price_inr=2_100.00,
    upside_pct=13.7,
    revenue_cr=38_994,
    pat_margin_pct=20.4,
    quarter="Q2 FY25",
    key_positive="Deal wins up 34% YoY, large deal TCV $2.9B",
    key_risk="USDINR headwind, discretionary spend still weak",
    triggered_by="announcement",
)

# ---------------------------------------------------------------------------
# Individual tests
# ---------------------------------------------------------------------------


def _test_whatsapp() -> tuple[bool, str]:
    """Test 1 — WhatsApp format preview.

    Returns (passed, detail) where detail is the failure message or the
    char-count on success.
    """
    msg = format_whatsapp(MOCK_SIGNAL)

    print()
    print(f"  {_THIN}")
    print("  WhatsApp preview:")
    print(f"  {_THIN}")
    for line in msg.splitlines():
        print(f"  {line}")
    print(f"  {_THIN}")

    checks = [
        ("INFY" in msg,      "'INFY' not found in WhatsApp message"),
        ("BUY"  in msg,      "'BUY' not found in WhatsApp message"),
        ("SEBI" in msg,      "SEBI disclaimer missing from WhatsApp message"),
        ("₹2,100" in msg,    "Target price '₹2,100' not found in WhatsApp message"),
    ]
    for ok, reason in checks:
        if not ok:
            return False, reason

    return True, f"{len(msg)} chars"


def _test_telegram() -> tuple[bool, str]:
    """Test 2 — Telegram format preview."""
    msg = format_telegram(MOCK_SIGNAL)

    print()
    print(f"  {_THIN}")
    print("  Telegram preview:")
    print(f"  {_THIN}")
    for line in msg.splitlines():
        print(f"  {line}")
    print(f"  {_THIN}")

    checks = [
        ("<b>"    in msg,  "'<b>' HTML tag missing — Telegram parse_mode=HTML broken"),
        ("13.7%"  in msg,  "Upside pct '13.7%' not found in Telegram message"),
        ("INFY"   in msg,  "'INFY' not found in Telegram message"),
        ("SEBI"   in msg,  "SEBI disclaimer missing from Telegram message"),
        ("20.4%"  in msg,  "PAT margin '20.4%' not found in Telegram message"),
    ]
    for ok, reason in checks:
        if not ok:
            return False, reason

    return True, f"{len(msg)} chars"


def _test_sms() -> tuple[bool, str]:
    """Test 3 — SMS format + 160-char hard limit."""
    sms = format_sms(MOCK_SIGNAL)

    print()
    print(f"  {_THIN}")
    print("  SMS preview:")
    print(f"  {_THIN}")
    print(f"  {sms}")
    print(f"  {_THIN}")

    checks = [
        (len(sms) <= 160, f"SMS body is {len(sms)} chars — exceeds 160-char GSM-7 limit"),
        ("INFY"    in sms, "'INFY' not found in SMS"),
        ("BUY"     in sms, "'BUY' not found in SMS"),
        ("Not SEBI reg." in sms, "Abbreviated SEBI disclaimer missing from SMS"),
    ]
    for ok, reason in checks:
        if not ok:
            return False, reason

    return True, f"{len(sms)} chars"


async def _test_dispatch() -> tuple[bool, str]:
    """Test 4 — Full dry_run dispatch (exercises the entire dispatcher path)."""
    result = await dispatch_alert(MOCK_SIGNAL, dry_run=True)

    checks = [
        (result.get("whatsapp") is True,  "result['whatsapp'] is not True"),
        (result.get("telegram") is True,  "result['telegram'] is not True"),
        (result.get("sms")      is True,  "result['sms'] is not True"),
        (result.get("dry_run")  is True,  "result['dry_run'] is not True"),
        (set(result.keys()) == {"whatsapp", "telegram", "sms", "dry_run"},
         f"unexpected keys in result: {set(result.keys())}"),
    ]
    for ok, reason in checks:
        if not ok:
            return False, reason

    channels_ok = sum(1 for k, v in result.items() if k != "dry_run" and v)
    return True, f"{channels_ok}/3 channels confirmed"


# ---------------------------------------------------------------------------
# Main test runner
# ---------------------------------------------------------------------------


async def _run_tests() -> bool:
    """Execute all four tests, print formatted results, return overall ok."""
    print()
    print(_SEP)
    print("  MarketPulse India — Alert Channel Smoke Test")
    print(f"  Signal: {MOCK_SIGNAL.nse_symbol} {MOCK_SIGNAL.signal_direction} "
          f"@ ₹{MOCK_SIGNAL.current_price_inr:,.2f} "
          f"→ ₹{MOCK_SIGNAL.target_price_inr:,.2f} "
          f"(+{MOCK_SIGNAL.upside_pct:.1f}%)")
    print(_SEP)

    results: list[tuple[str, bool, str]] = []

    # ── Test 1: WhatsApp ─────────────────────────────────────────────────────
    try:
        ok, detail = _test_whatsapp()
        results.append(("WhatsApp format", ok, detail))
    except Exception as exc:  # noqa: BLE001
        results.append(("WhatsApp format", False, f"unexpected exception: {exc}"))

    # ── Test 2: Telegram ─────────────────────────────────────────────────────
    try:
        ok, detail = _test_telegram()
        results.append(("Telegram format", ok, detail))
    except Exception as exc:  # noqa: BLE001
        results.append(("Telegram format", False, f"unexpected exception: {exc}"))

    # ── Test 3: SMS ──────────────────────────────────────────────────────────
    try:
        ok, detail = _test_sms()
        results.append(("SMS length", ok, detail))
    except Exception as exc:  # noqa: BLE001
        results.append(("SMS length", False, f"unexpected exception: {exc}"))

    # ── Test 4: dry_run dispatch ─────────────────────────────────────────────
    try:
        ok, detail = await _test_dispatch()
        results.append(("dry_run dispatch", ok, detail))
    except Exception as exc:  # noqa: BLE001
        results.append(("dry_run dispatch", False, f"unexpected exception: {exc}"))

    # ── Summary ──────────────────────────────────────────────────────────────
    print()
    print(_SEP)
    passed = 0
    for name, ok, detail in results:
        if ok:
            print(f"  ✅ {name} ({detail}) — PASS")
            passed += 1
        else:
            print(f"  ❌ {name} — FAIL: {detail}")

    total = len(results)
    print(_SEP)
    print(f"  {passed}/{total} tests passed")
    print(_SEP)
    print()

    return passed == total


def main() -> None:
    """Entry point.

    Forces SelectorEventLoop on Windows — the default ProactorEventLoop
    breaks aiohttp (used by the WhatsApp sender) and asyncio.to_thread
    with selector-based threads.
    """
    if sys.platform == "win32":
        loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
        ok = loop.run_until_complete(_run_tests())
        loop.close()
    else:
        ok = asyncio.run(_run_tests())

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
