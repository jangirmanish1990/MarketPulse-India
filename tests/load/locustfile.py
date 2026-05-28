"""tests/load/locustfile.py — Locust load test for MarketPulse India API.

Target: 20 concurrent users, 4/s spawn, 30 s run.

Task mix (weights):
  3  — POST /api/analyze/{nse_symbol}  (heavy, agent pipeline)
  2  — GET  /api/signals/recent        (read-heavy)
  1  — GET  /api/sector/rankings/{sector}  (sector view, may 404)
  1  — GET  /health                    (baseline latency)

Auth
----
On start each user tries to obtain a JWT via POST /api/auth/login
(form-encoded, OAuth2PasswordRequestForm).  If auth fails the user
continues with an empty token so the /health task is still exercised.

Usage
-----
    locust -f tests/load/locustfile.py --headless \\
        --users 20 --spawn-rate 4 --run-time 30s \\
        --host http://localhost:8000 \\
        --html tests/load/report.html

Or via the helper script:
    python scripts/run_load_test.py
"""

from __future__ import annotations

import random

from locust import HttpUser, between, task


class MarketPulseUser(HttpUser):
    wait_time = between(1, 3)
    host = "http://localhost:8000"

    # ------------------------------------------------------------------ #
    #  Auth                                                                #
    # ------------------------------------------------------------------ #

    def on_start(self) -> None:
        """Obtain JWT once per simulated user at startup."""
        # OAuth2PasswordRequestForm requires form-encoded data, not JSON.
        resp = self.client.post(
            "/api/auth/login",
            data={"username": "testuser", "password": "testpass123"},
            name="/api/auth/login",
        )
        if resp.status_code == 200:
            self.token: str = resp.json().get("access_token", "")
        else:
            # Auth failed (backend may not be seeded with testuser).
            # Continue with empty token — /health is still exercisable.
            self.token = ""

    # ------------------------------------------------------------------ #
    #  Tasks                                                               #
    # ------------------------------------------------------------------ #

    @task(3)
    def analyze_stock(self) -> None:
        """Trigger the full agent pipeline for a random large-cap symbol."""
        symbol = random.choice(["TCS", "INFY", "HDFCBANK", "RELIANCE", "WIPRO", "SBIN"])
        self.client.post(
            f"/api/analyze/{symbol}",
            headers={"Authorization": f"Bearer {self.token}"},
            name="/api/analyze",
        )

    @task(2)
    def get_signals(self) -> None:
        """Fetch the 20 most-recent signals."""
        self.client.get(
            "/api/signals/recent",
            headers={"Authorization": f"Bearer {self.token}"},
            name="/api/signals",
        )

    @task(1)
    def sector_rankings(self) -> None:
        """Fetch sector rankings via the POST endpoint."""
        sector = random.choice(["IT", "Banking", "FMCG"])
        self.client.post(
            "/api/sector/analyze",
            json={"sector": sector},
            headers={"Authorization": f"Bearer {self.token}"},
            name="/api/sector/rankings/{sector}",
        )

    @task(1)
    def health_check(self) -> None:
        """Baseline latency probe — no auth required."""
        self.client.get("/health", name="/health")
