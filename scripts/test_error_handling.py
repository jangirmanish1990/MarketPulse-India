"""Smoke-test the MarketPulse India error handling layer.

Requires the FastAPI server to be running locally:
    make dev   (or: uvicorn backend.main:app --reload)

Usage:
    python scripts/test_error_handling.py

Prints PASSED or FAILED for each case, exits 0 on full pass.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Force UTF-8 on Windows cp1252 consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import httpx  # noqa: E402

BASE_URL = "http://localhost:8000"
OK = "[PASS]"
FAIL = "[FAIL]"


def _check(label: str, ok: bool, detail: str = "") -> bool:
    tag = OK if ok else FAIL
    suffix = f"  ({detail})" if detail else ""
    print(f"  {tag}  {label}{suffix}")
    return ok


async def _get_token(client: httpx.AsyncClient) -> str | None:
    r = await client.post(
        f"{BASE_URL}/api/auth/login",
        data={"username": "manish@marketpulse.in", "password": "demo123"},
    )
    if r.status_code == 200:
        return r.json()["access_token"]
    return None


async def test_errors() -> bool:
    results: list[bool] = []

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Obtain a valid JWT so auth-protected stock endpoints reach the DB layer.
        token = await _get_token(client)
        auth_headers = {"Authorization": f"Bearer {token}"} if token else {}

        # ── Test 1: Invalid stock symbol → 404 ─────────────────────────────
        r = await client.get(f"{BASE_URL}/api/stocks/INVALIDXYZ999", headers=auth_headers)
        data = r.json()
        ok = (
            r.status_code == 404
            and data.get("error_code") == "STOCK_NOT_FOUND"
            and "trace_id" in data
            and "timestamp_ist" in data
        )
        results.append(_check("Invalid stock → 404 STOCK_NOT_FOUND", ok, data.get("error_code", "")))

        # ── Test 2: Missing auth → 401 ──────────────────────────────────────
        r = await client.get(f"{BASE_URL}/api/watchlist")
        ok = r.status_code == 401 and r.json().get("error_code") == "INVALID_TOKEN"
        results.append(_check("No auth token → 401 INVALID_TOKEN", ok, r.json().get("error_code", "")))

        # ── Test 3: Wrong webhook secret → 401 ─────────────────────────────
        r = await client.post(
            f"{BASE_URL}/api/webhook/announcement",
            headers={"X-Webhook-Secret": "wrong-secret"},
            json={
                "nse_symbol": "INFY",
                "announcement_type": "quarterly_results",
                "announcement_raw": "Test",
                "exchange": "NSE",
            },
        )
        ok = r.status_code == 401 and r.json().get("error_code") == "WEBHOOK_AUTH_FAILED"
        results.append(_check("Bad webhook secret → 401 WEBHOOK_AUTH_FAILED", ok, r.json().get("error_code", "")))

        # ── Test 4: Unknown route → 404 ─────────────────────────────────────
        r = await client.get(f"{BASE_URL}/api/nonexistent-route")
        data = r.json()
        ok = r.status_code == 404 and data.get("error_code") == "NOT_FOUND" and "trace_id" in data
        results.append(_check("Unknown route → 404 NOT_FOUND", ok, data.get("error_code", "")))

        # ── Test 5: Response shape — required fields always present ─────────
        r = await client.get(f"{BASE_URL}/api/stocks/INVALIDSHAPE", headers=auth_headers)
        data = r.json()
        required = {"error", "error_code", "message", "retriable", "trace_id", "timestamp_ist"}
        missing = required - set(data.keys())
        ok = len(missing) == 0
        results.append(
            _check("Error shape has required fields", ok, f"missing={missing or 'none'}")
        )

        # ── Test 6: X-Request-ID header is echoed as trace_id ───────────────
        custom_id = "test-abc-123"
        r = await client.get(
            f"{BASE_URL}/api/stocks/BADXYZ",
            headers={**auth_headers, "X-Request-ID": custom_id},
        )
        data = r.json()
        ok = data.get("trace_id") == custom_id
        results.append(_check("X-Request-ID echoed as trace_id", ok, data.get("trace_id", "")))

    return all(results)


def main() -> None:
    sep = "=" * 56
    print(sep)
    print("MarketPulse India — Error Handling Smoke Test")
    print(sep)

    passed = asyncio.run(test_errors())

    print(f"\n{sep}")
    print("Error Handling PASSED" if passed else "Error Handling FAILED")
    print(sep)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
