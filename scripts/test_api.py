"""End-to-end API smoke test for MarketPulse India.

Run the server first:
    uvicorn backend.main:app --reload

Then in another terminal:
    python scripts/test_api.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

import httpx

BASE_URL = "http://localhost:8000"


async def test_all_endpoints() -> None:
    async with httpx.AsyncClient(timeout=30.0) as client:

        # 1. Health check
        r = await client.get(f"{BASE_URL}/health")
        assert r.status_code == 200, f"Health failed: {r.status_code} {r.text}"
        data = r.json()
        print(f"Health: {data['status']} | Market: {data['market_status']}")

        # 2. Login
        r = await client.post(
            f"{BASE_URL}/api/auth/login",
            data={"username": "manish@marketpulse.in", "password": "demo123"},
        )
        assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("Auth: Login OK | Token received")

        # 3. /auth/me
        r = await client.get(f"{BASE_URL}/api/auth/me", headers=headers)
        assert r.status_code == 200, f"/me failed: {r.status_code}"
        me = r.json()
        print(f"Auth/me: {me['name']} <{me['email']}>")

        # 4. Market summary
        r = await client.get(f"{BASE_URL}/api/market/summary", headers=headers)
        assert r.status_code == 200, f"Market summary failed: {r.status_code} {r.text}"
        data = r.json()
        nifty = data["nifty50"]["value"]
        usdinr = data["usd_inr"]
        print(f"Market: Nifty={nifty} | USD/INR={usdinr} | Status={data['market_status']}")

        # 5. Results calendar
        r = await client.get(f"{BASE_URL}/api/market/results-calendar", headers=headers)
        assert r.status_code == 200, f"Results calendar failed: {r.status_code}"
        cal = r.json()
        print(f"Calendar: {len(cal['upcoming'])} upcoming seasons")

        # 6. Stock list (all)
        r = await client.get(f"{BASE_URL}/api/stocks", headers=headers)
        assert r.status_code == 200, f"Stock list failed: {r.status_code} {r.text}"
        print(f"Stocks: {r.json()['total']} total stocks")

        # 7. Nifty50 only
        r = await client.get(f"{BASE_URL}/api/stocks?nifty50_only=true", headers=headers)
        assert r.status_code == 200
        print(f"Stocks: {r.json()['total']} Nifty50 stocks")

        # 8. Stock detail (pick the first stock returned)
        all_stocks = (await client.get(f"{BASE_URL}/api/stocks", headers=headers)).json()["stocks"]
        if all_stocks:
            first_sym = all_stocks[0]["symbol"]
            r = await client.get(f"{BASE_URL}/api/stocks/{first_sym}", headers=headers)
            assert r.status_code == 200, f"Stock detail failed: {r.status_code}"
            detail = r.json()
            print(f"Stock detail: {detail['symbol']} — {detail['company_name']}")

            # 9. Add to watchlist
            r = await client.post(f"{BASE_URL}/api/watchlist/{first_sym}", headers=headers)
            assert r.status_code == 200, f"Watchlist add failed: {r.status_code} {r.text}"
            print(f"Watchlist: {first_sym} added = {r.json()['added']}")

            # 10. Get watchlist
            r = await client.get(f"{BASE_URL}/api/watchlist", headers=headers)
            assert r.status_code == 200, f"Watchlist get failed: {r.status_code}"
            wl = r.json()
            print(f"Watchlist: {len(wl['items'])} stock(s)")

            # 11. Trigger analysis (non-blocking)
            r = await client.post(f"{BASE_URL}/api/analyze/{first_sym}", headers=headers)
            assert r.status_code == 200, f"Analyze failed: {r.status_code} {r.text}"
            session_id = r.json()["session_id"]
            print(f"Analysis: Queued | session_id={session_id}")

            # 12. Latest signal (may be None on fresh install)
            r = await client.get(f"{BASE_URL}/api/analyze/{first_sym}/latest", headers=headers)
            assert r.status_code == 200, f"Latest signal failed: {r.status_code}"
            sig = r.json()
            if sig:
                print(
                    f"Latest signal: {sig['direction']} | "
                    f"Confidence={sig['confidence']:.0%}"
                )
            else:
                print("Latest signal: none yet (pipeline still running)")

            # 13. Remove from watchlist
            r = await client.delete(f"{BASE_URL}/api/watchlist/{first_sym}", headers=headers)
            assert r.status_code == 200
            print(f"Watchlist: {first_sym} removed = {r.json()['removed']}")
        else:
            print("No stocks in DB — skipping stock-dependent tests (run /seed-corpus first)")

        # 14. Recent signals
        r = await client.get(f"{BASE_URL}/api/signals/recent", headers=headers)
        assert r.status_code == 200, f"Recent signals failed: {r.status_code}"
        signals = r.json()["signals"]
        if signals:
            s = signals[0]
            print(
                f"Signals: Latest = {s['direction']} | "
                f"Confidence={s['confidence']:.0%}"
            )
        else:
            print("Signals: none in DB yet")

        print()
        print("All API tests PASSED")


if __name__ == "__main__":
    asyncio.run(test_all_endpoints())
