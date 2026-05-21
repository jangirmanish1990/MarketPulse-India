"""WebSocket streaming smoke-test.

Usage:
    python scripts/test_websocket.py

Expects a running API at localhost:8000 with the demo user seeded.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import websockets

BASE_URL = "http://localhost:8000"
WS_BASE = "ws://localhost:8000"

_DIRECTION_EMOJI: dict[str, str] = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡"}


async def test_websocket_streaming() -> None:
    # ── Step 1: login ───────────────────────────────────────────────────────
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BASE_URL}/api/auth/login",
            data={"username": "manish@marketpulse.in", "password": "demo123"},
        )
        r.raise_for_status()
        token: str = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # ── Step 2: trigger analysis ────────────────────────────────────────
        r = await client.post(f"{BASE_URL}/api/analyze/TCS", headers=headers)
        r.raise_for_status()
        result = r.json()

    session_id: str = result["session_id"]
    ws_url: str = result["ws_url"]
    print(f"Analysis triggered: session={session_id}")
    print(f"Connecting to:      {ws_url}")
    print("=" * 60)

    # ── Step 3: stream events ───────────────────────────────────────────────
    async with websockets.connect(ws_url) as ws:  # type: ignore[attr-defined]
        print("Connected to WebSocket stream\nWatching agent execute...\n")

        while True:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=120)
                event: dict[str, object] = json.loads(raw)
                ev_type: str = str(event.get("type", ""))
                ts: str = str(event.get("ist_timestamp", ""))[:19]

                if ev_type == "connected":
                    print(f"[{ts}] Connected | Market: {event.get('market_status')}")

                elif ev_type == "pipeline_start":
                    print(f"\n[{ts}] Pipeline started: {event.get('symbol')}")
                    print("-" * 60)

                elif ev_type == "node_start":
                    icon = event.get("icon", "▶")
                    label = event.get("label", event.get("node", ""))
                    print(f"[{ts}] {icon} RUNNING: {label}")

                elif ev_type == "node_complete":
                    icon = event.get("icon", "✓")
                    label = event.get("label", event.get("node", ""))
                    node = str(event.get("node", ""))
                    summary: dict[str, object] = event.get("summary", {})  # type: ignore[assignment]

                    suffix = ""
                    if node == "fetch_market_data":
                        ltp = summary.get("ltp", 0)
                        nifty = summary.get("nifty", 0)
                        suffix = f"LTP=₹{ltp:.2f} | Nifty={nifty:.2f}"
                    elif node == "grade_documents":
                        suffix = f"{summary.get('relevant', 0)}/{summary.get('total', 0)} relevant"
                    elif node == "score_signal":
                        direction = summary.get("direction", "?")
                        conf = summary.get("confidence") or 0
                        suffix = f"{direction} | {conf:.0%}"

                    line = f"[{ts}] {icon} DONE:    {label}"
                    if suffix:
                        line += f" → {suffix}"
                    print(line)

                elif ev_type == "tool_call":
                    print(f"[{ts}]    {event.get('message')}")

                elif ev_type == "signal_complete":
                    signal: dict[str, object] = event.get("signal", {})  # type: ignore[assignment]
                    direction = str(signal.get("direction", "?"))
                    emoji = _DIRECTION_EMOJI.get(direction, "⚪")
                    target = signal.get("target_price_inr", 0)
                    upside = signal.get("upside_pct", 0)
                    confidence = signal.get("confidence", 0)
                    horizon = signal.get("time_horizon_days", 60)
                    rationale = signal.get("rationale", "")
                    print("\n" + "=" * 60)
                    print(f"FINAL SIGNAL: {emoji} {direction}")
                    print(f"Target:       ₹{target:.0f} ({upside:+.1f}%)")  # type: ignore[str-format]
                    print(f"Confidence:   {confidence:.0%}")  # type: ignore[str-format]
                    print(f"Horizon:      {horizon} days")
                    print(f"Rationale:    {rationale}")
                    print("=" * 60)
                    print("\nWebSocket streaming test PASSED ✅")
                    break

                elif ev_type == "heartbeat":
                    pass  # silently ignore

                elif ev_type == "error":
                    print(f"\nERROR: {event.get('error')}")
                    break

            except TimeoutError:
                print("Timeout waiting for events — no message in 120 s")
                break


if __name__ == "__main__":
    asyncio.run(test_websocket_streaming())
