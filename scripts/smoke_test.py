"""scripts/smoke_test.py — full end-to-end smoke test for MarketPulse India.

Validates the complete stack before making the repo public:
  1. Backend health
  2. Authentication (JWT)
  3. Analysis triggered (HDFCBANK)
  4. WebSocket 9-node pipeline trace
  5. Signal persisted in DB
  6. Sector analysis (Banking)

Usage:
    python scripts/smoke_test.py
    python scripts/smoke_test.py --base-url http://your-alb-dns.ap-south-1.elb.amazonaws.com

Exit code 0 → all checks passed.
Exit code 1 → one or more checks failed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any

# Windows: Proactor loop required by websockets; Selector loop required by
# psycopg/asyncpg. We only need asyncio.run() here — not the DB drivers —
# so Proactor is correct for this script.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())  # type: ignore[attr-defined]

# Force UTF-8 so ✅/❌/═ characters don't crash on Windows cp1252
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

try:
    import httpx
except ImportError:
    print("httpx not installed. Run: pip install httpx")
    sys.exit(1)

try:
    import websockets  # type: ignore[import-untyped]
    import websockets.exceptions
except ImportError:
    print("websockets not installed. Run: pip install websockets")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_BASE_URL = "http://localhost:8000"
DEMO_USERNAME    = "testuser"
DEMO_PASSWORD    = "testpass123"
WS_TIMEOUT_S     = 45      # seconds to wait for pipeline completion
ANALYSIS_SYMBOL  = "HDFCBANK"

ANNOUNCEMENT_RAW = (
    "HDFC Bank Q2 FY25: Net Interest Income ₹30,114 Cr (+10% YoY). "
    "PAT ₹16,821 Cr (+5.3% YoY). NIM 3.46%. GNPA 1.36% stable. "
    "Management: credit growth moderating to 12-14%."
)

_SEP   = "═" * 50
_THIN  = "─" * 50


# ---------------------------------------------------------------------------
# State shared across checks
# ---------------------------------------------------------------------------

@dataclass
class RunState:
    base_url:   str  = DEFAULT_BASE_URL
    token:      str  = ""
    session_id: str  = ""
    results:    list[tuple[str, bool, str]] = field(default_factory=list)

    def ws_url(self) -> str:
        return self.base_url.replace("http://", "ws://").replace("https://", "wss://")

    def record(self, label: str, passed: bool, detail: str = "") -> None:
        self.results.append((label, passed, detail))
        icon = "✅" if passed else "❌"
        line = f"  {icon} {label}"
        if detail:
            line += f" — {detail}"
        print(line)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

async def check_health(state: RunState, client: httpx.AsyncClient) -> bool:
    try:
        r = await client.get(f"{state.base_url}/health", timeout=10)
        r.raise_for_status()
        body = r.json()
        assert body.get("status") in ("ok", "healthy"), f"status={body.get('status')}"
        assert "now_ist" in body or "ist_time" in body, "no IST time field"
        ist_time = body.get("now_ist") or body.get("ist_time", "unknown")
        market   = body.get("market_status", body.get("market_open", "unknown"))
        state.record(
            "Backend health",
            True,
            f"{ist_time}  market={market}",
        )
        return True
    except Exception as exc:
        state.record("Backend health", False, str(exc)[:100])
        return False


async def check_auth(state: RunState, client: httpx.AsyncClient) -> bool:
    try:
        r = await client.post(
            f"{state.base_url}/api/auth/login",
            data={"username": DEMO_USERNAME, "password": DEMO_PASSWORD},
            timeout=10,
        )
        r.raise_for_status()
        body = r.json()
        assert "access_token" in body, f"no access_token in {list(body.keys())}"
        state.token = body["access_token"]
        state.record("Authentication", True, "JWT issued")
        return True
    except Exception as exc:
        state.record("Authentication", False, str(exc)[:100])
        return False


async def check_trigger_analysis(state: RunState, client: httpx.AsyncClient) -> bool:
    try:
        r = await client.post(
            f"{state.base_url}/api/analyze/{ANALYSIS_SYMBOL}",
            headers={"Authorization": f"Bearer {state.token}"},
            timeout=15,
        )
        r.raise_for_status()
        body = r.json()
        assert "session_id" in body,  f"no session_id in {list(body.keys())}"
        assert body.get("status") == "running", f"status={body.get('status')}"
        state.session_id = body["session_id"]
        state.record(
            f"Analysis triggered ({ANALYSIS_SYMBOL})",
            True,
            f"session {state.session_id[:8]}…",
        )
        return True
    except Exception as exc:
        state.record(f"Analysis triggered ({ANALYSIS_SYMBOL})", False, str(exc)[:100])
        return False


async def check_websocket_pipeline(state: RunState) -> bool:
    label = "WebSocket 9-node trace"
    if not state.session_id:
        state.record(label, False, "skipped — no session_id")
        return False

    ws_uri = f"{state.ws_url()}/ws/analyze/{state.session_id}?token={state.token}"
    node_events: list[dict[str, Any]] = []
    signal_event: dict[str, Any] | None = None
    deadline = time.monotonic() + WS_TIMEOUT_S

    try:
        async with websockets.connect(ws_uri, open_timeout=10) as ws:
            while time.monotonic() < deadline:
                remaining = deadline - time.monotonic()
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 5.0))
                except asyncio.TimeoutError:
                    continue

                msg: dict[str, Any] = json.loads(raw)
                event = msg.get("event", "")

                if event == "node_complete":
                    node_events.append(msg)
                elif event == "signal_ready":
                    signal_event = msg
                elif event == "pipeline_end":
                    break

        # Assertions
        assert len(node_events) >= 5, (
            f"only {len(node_events)} node_complete events (expected ≥5)"
        )
        assert signal_event is not None, "no signal_ready event received"
        direction = signal_event.get("direction", "")
        assert direction in ("BUY", "HOLD", "SELL"), f"invalid direction: {direction!r}"
        disclaimer = str(signal_event.get("sebi_disclaimer", "")).lower()
        assert "sebi" in disclaimer, "SEBI disclaimer missing from signal_ready"

        # Build trace output
        print()
        print("    Pipeline trace:")
        for i, ev in enumerate(node_events, 1):
            node_name = ev.get("node", f"node_{i}")
            ms        = ev.get("duration_ms", ev.get("elapsed_ms", "?"))
            print(f"      → {i:>2}. {node_name:<30} ({ms}ms)")
        conf  = signal_event.get("confidence", 0)
        conf_pct = f"{conf * 100:.0f}%" if isinstance(conf, float) else str(conf)
        print(f"      → signal: {direction}  confidence {conf_pct}")
        print()

        state.record(
            label,
            True,
            f"{len(node_events)} nodes  →  {direction} {conf_pct}",
        )
        return True

    except Exception as exc:
        state.record(label, False, str(exc)[:120])
        return False


async def check_signal_in_db(state: RunState, client: httpx.AsyncClient) -> bool:
    label = "Signal persisted in DB"
    try:
        r = await client.get(
            f"{state.base_url}/api/signals/recent",
            headers={"Authorization": f"Bearer {state.token}"},
            timeout=10,
        )
        r.raise_for_status()
        body = r.json()
        signals = body.get("signals", [])
        assert len(signals) >= 1, "no signals returned"
        sig = signals[0]
        assert "sebi_disclaimer" in sig, "sebi_disclaimer missing from signal"
        symbol    = sig.get("nse_symbol", sig.get("symbol", "?"))
        direction = sig.get("direction", "?")
        state.record(label, True, f"{symbol} {direction}")
        return True
    except Exception as exc:
        state.record(label, False, str(exc)[:100])
        return False


async def check_sector_analysis(state: RunState, client: httpx.AsyncClient) -> bool:
    label = "Sector analysis (Banking)"
    try:
        r = await client.post(
            f"{state.base_url}/api/sector/analyze",
            headers={"Authorization": f"Bearer {state.token}"},
            json={"sector": "Banking"},
            timeout=60,
        )
        r.raise_for_status()
        body = r.json()
        winner  = body.get("sector_winner", "?")
        sig     = body.get("sector_signal", body.get("signal", "?"))
        peers   = body.get("peer_rankings", [])
        assert winner, "sector_winner missing"
        assert sig in ("bullish", "neutral", "bearish"), f"unexpected sector_signal: {sig!r}"
        assert len(peers) >= 1, f"only {len(peers)} peer_rankings"
        state.record(label, True, f"winner: {winner}  signal: {sig}  peers: {len(peers)}")
        return True
    except Exception as exc:
        state.record(label, False, str(exc)[:100])
        return False


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_all(base_url: str) -> int:
    state = RunState(base_url=base_url)

    print()
    print(f"  {_SEP}")
    print("    MarketPulse India — Launch Smoke Test")
    print(f"    Target: {base_url}")
    print(f"  {_THIN}")
    print()

    async with httpx.AsyncClient() as client:

        # Check 1 — health (always attempt regardless of prior failures)
        ok1 = await check_health(state, client)

        # Check 2 — auth (need token for everything downstream)
        ok2 = await check_auth(state, client)

        # Check 3 — trigger analysis (needs auth)
        ok3 = await check_trigger_analysis(state, client) if ok2 else (
            state.record(f"Analysis triggered ({ANALYSIS_SYMBOL})", False, "skipped — auth failed")
            or False
        )

        # Check 4 — WebSocket trace (needs session_id from check 3)
        ok4 = await check_websocket_pipeline(state)

        # Check 5 — signal in DB (needs auth; slight delay gives pipeline time to write)
        if ok2:
            await asyncio.sleep(2)
        ok5 = await check_signal_in_db(state, client) if ok2 else (
            state.record("Signal persisted in DB", False, "skipped — auth failed")
            or False
        )

        # Check 6 — sector analysis (needs auth)
        ok6 = await check_sector_analysis(state, client) if ok2 else (
            state.record("Sector analysis (Banking)", False, "skipped — auth failed")
            or False
        )

    passed = sum(1 for _, ok, _ in state.results if ok)
    total  = len(state.results)
    all_ok = passed == total

    print()
    print(f"  {_SEP}")
    print("    MarketPulse India — Launch Smoke Test")
    print(f"  {_SEP}")
    for label, ok, detail in state.results:
        icon = "✅" if ok else "❌"
        print(f"    {icon} {label}")
    print(f"  {_SEP}")
    if all_ok:
        print(f"    {passed}/{total} checks passed — READY TO LAUNCH 🚀")
    else:
        print(f"    {passed}/{total} checks passed — fix failures before launch")
    print(f"  {_SEP}")
    print()

    return 0 if all_ok else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="MarketPulse India smoke test")
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"API base URL (default: {DEFAULT_BASE_URL})",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(run_all(args.base_url)))


if __name__ == "__main__":
    main()
