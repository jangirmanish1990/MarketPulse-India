"""scripts/run_load_test.py — Headless Locust runner + results summary.

Usage
-----
    python scripts/run_load_test.py
    uv run python scripts/run_load_test.py

What it does
------------
1. Verifies the backend is reachable at http://localhost:8000/health.
2. Runs Locust headless (20 users, 4/s spawn, 30 s) in a subprocess.
3. Saves HTML report → tests/load/report.html
4. Saves CSV stats  → tests/load/stats_*.csv  (locust auto-names them)
5. Parses the CSV and prints a formatted summary table:

   ┌──────────────────────────────────────┬────────┬────────┬───────┐
   │ Endpoint                             │  RPS   │  P95   │ Fails │
   ├──────────────────────────────────────┼────────┼────────┼───────┤
   │ /api/analyze                         │   6.3  │ 4500ms │     0 │
   │ /api/signals                         │   4.2  │  210ms │     0 │
   │ /api/sector/rankings/{sector}        │   2.1  │  980ms │     3 │
   │ /health                              │   2.1  │   18ms │     0 │
   │ Aggregated                           │  14.7  │ 4500ms │     3 │
   └──────────────────────────────────────┴────────┴────────┴───────┘

6. Determines a PASS / FAIL verdict:

   Pass criterion
   --------------
   * Overall failure rate < 5 % across all endpoints.

   RPS is shown for information only — no RPS gate.  The LangGraph
   agent pipeline takes 2–3 s per request, so aggregate RPS is naturally
   low (~4) even at full concurrency.  That is expected and acceptable.

   Auth-failure note
   -----------------
   If POST /api/auth/login itself failed for every request (e.g. testuser
   not seeded), all 401s on auth-gated endpoints are flagged as auth issues,
   not application failures.
   Run ``python scripts/seed_test_user.py`` to seed the test credential.

7. Prints final verdict:

   ✅ Load test PASSED — 4.1 RPS, 0.0% failures
   Core endpoints responding under 20 concurrent users

   or:

   ❌ Load test FAILED — 18.3% failure rate (threshold < 5%)

Exit codes
----------
  0 — test completed and verdict PASSED
  1 — backend unreachable (test not started)
  2 — locust subprocess exited with non-zero status
  3 — test completed but verdict FAILED (failure rate ≥ 5 %)
"""

from __future__ import annotations

import csv
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ROOT        = Path(__file__).resolve().parents[1]
_LOCUSTFILE  = _ROOT / "tests" / "load" / "locustfile.py"
_REPORT_HTML = _ROOT / "tests" / "load" / "report.html"
_REPORT_CSV  = _ROOT / "tests" / "load" / "stats"   # locust appends _stats.csv
_HOST        = "http://localhost:8000"
_USERS       = 20
_SPAWN_RATE  = 4
_RUN_TIME    = "30s"
_MAX_FAIL_PCT = 5.0   # verdict threshold — overall failure rate must be below this

_SEP  = "═" * 66
_THIN = "─" * 66


# ---------------------------------------------------------------------------
# Small numeric helpers
# ---------------------------------------------------------------------------


def _safe_float(v: object, default: float = 0.0) -> float:
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _safe_int(v: object, default: int = 0) -> int:
    try:
        return int(float(v))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Backend reachability probe
# ---------------------------------------------------------------------------


def _backend_reachable() -> bool:
    """Return True when /health responds with status 200."""
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(f"{_HOST}/health", timeout=5) as resp:
            return resp.status == 200
    except (urllib.error.URLError, OSError):
        return False


# ---------------------------------------------------------------------------
# Locust subprocess runner
# ---------------------------------------------------------------------------


def _run_locust() -> int:
    """Execute locust as a subprocess and return its exit code."""
    _REPORT_HTML.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "locust",
        "-f", str(_LOCUSTFILE),
        "--headless",
        f"--users={_USERS}",
        f"--spawn-rate={_SPAWN_RATE}",
        f"--run-time={_RUN_TIME}",
        f"--host={_HOST}",
        f"--html={_REPORT_HTML}",
        f"--csv={_REPORT_CSV}",
        "--only-summary",
    ]

    print(f"  Running: {' '.join(cmd[2:])}")
    print()

    result = subprocess.run(cmd, cwd=_ROOT)
    return result.returncode


# ---------------------------------------------------------------------------
# CSV stats parser
# ---------------------------------------------------------------------------


def _parse_csv_stats() -> list[dict[str, str]]:
    """Read the locust *_stats.csv and return rows as list-of-dicts.

    Locust 2.x writes  <prefix>_stats.csv  where <prefix> is --csv value.
    Falls back to the most-recently-modified *_stats.csv in the load dir.
    """
    canonical = Path(str(_REPORT_CSV) + "_stats.csv")
    if not canonical.exists():
        candidates = list(_REPORT_HTML.parent.glob("*_stats.csv"))
        if not candidates:
            return []
        canonical = sorted(candidates, key=lambda p: p.stat().st_mtime)[-1]

    rows: list[dict[str, str]] = []
    with open(canonical, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(dict(row))
    return rows


# ---------------------------------------------------------------------------
# Summary table printer
# ---------------------------------------------------------------------------


def _print_summary(rows: list[dict[str, str]]) -> None:
    """Print the boxed Endpoint / RPS / P95 / Fails table."""
    if not rows:
        print("  ⚠️  No CSV stats found — check tests/load/ for report files.")
        return

    W_EP, W_RPS, W_P95, W_FAIL = 38, 8, 8, 7

    def _header() -> str:
        return (
            f"  ┌{'─'*W_EP}┬{'─'*W_RPS}┬{'─'*W_P95}┬{'─'*W_FAIL}┐\n"
            f"  │ {'Endpoint':<{W_EP-2}} │ {'RPS':>{W_RPS-2}} │ {'P95':>{W_P95-2}} │ {'Fails':>{W_FAIL-2}} │\n"
            f"  ├{'─'*W_EP}┼{'─'*W_RPS}┼{'─'*W_P95}┼{'─'*W_FAIL}┤"
        )

    def _row(name: str, rps: str, p95_ms: str, fails: str) -> str:
        name_t = (name[:W_EP-3] + "…") if len(name) > W_EP-2 else name
        return (
            f"  │ {name_t:<{W_EP-2}} │ {rps:>{W_RPS-2}} │ {p95_ms:>{W_P95-2}} │ {fails:>{W_FAIL-2}} │"
        )

    def _footer() -> str:
        return f"  └{'─'*W_EP}┴{'─'*W_RPS}┴{'─'*W_P95}┴{'─'*W_FAIL}┘"

    print(_header())

    aggregated_row: dict[str, str] | None = None
    for r in rows:
        name = r.get("Name", "").strip()
        if name.lower() in {"aggregated", ""}:
            aggregated_row = r
            continue

        rps    = f"{_safe_float(r.get('Requests/s')):.1f}"
        p95    = f"{_safe_int(r.get('95%'))}ms"
        fails  = str(_safe_int(r.get("Failure Count")))
        print(_row(name, rps, p95, fails))

    if aggregated_row:
        print(f"  ├{'─'*W_EP}┼{'─'*W_RPS}┼{'─'*W_P95}┼{'─'*W_FAIL}┤")
        rps   = f"{_safe_float(aggregated_row.get('Requests/s')):.1f}"
        p95   = f"{_safe_int(aggregated_row.get('95%'))}ms"
        fails = str(_safe_int(aggregated_row.get("Failure Count")))
        print(_row("Aggregated", rps, p95, fails))

    print(_footer())
    print()

    try:
        rel = _REPORT_HTML.relative_to(_ROOT)
    except ValueError:
        rel = _REPORT_HTML
    print(f"  HTML report → {rel}")


# ---------------------------------------------------------------------------
# Verdict logic
# ---------------------------------------------------------------------------


def _print_verdict(rows: list[dict[str, str]]) -> bool:
    """Evaluate pass/fail, print the verdict line, return True when passed.

    Pass criterion
    --------------
    Overall failure rate (Aggregated row) < _MAX_FAIL_PCT (5.0 %).

    RPS is informational only — no RPS gate.  The LangGraph agent pipeline
    takes 2–3 s per stock, so aggregate throughput is naturally ~4 RPS under
    20 concurrent users.  That is expected behaviour, not a failure.

    Auth-failure note
    -----------------
    If every /api/auth/login request failed, 401s on auth-gated endpoints
    are flagged as a configuration issue, not an application bug.
    Run ``python scripts/seed_test_user.py`` to seed the test credential.
    """
    if not rows:
        print()
        print("  ⚠️  No stats to evaluate — verdict skipped.")
        return False

    # Index rows by name for quick lookup.
    by_name: dict[str, dict[str, str]] = {}
    for r in rows:
        name = r.get("Name", "").strip()
        by_name[name] = r

    agg    = by_name.get("Aggregated") or by_name.get("aggregated")
    health = by_name.get("/health")
    auth   = by_name.get("/api/auth/login")

    # ── Overall failure rate (gate) ───────────────────────────────────────────
    overall_fail_pct = 100.0
    overall_rps      = 0.0
    if agg:
        total = _safe_int(agg.get("Request Count"))
        fails = _safe_int(agg.get("Failure Count"))
        overall_fail_pct = (fails / total * 100) if total > 0 else 0.0
        overall_rps      = _safe_float(agg.get("Requests/s"))

    passed = overall_fail_pct < _MAX_FAIL_PCT

    # ── /health failure rate (informational) ─────────────────────────────────
    health_fail_pct = 0.0
    if health:
        total = _safe_int(health.get("Request Count"))
        fails = _safe_int(health.get("Failure Count"))
        health_fail_pct = (fails / total * 100) if total > 0 else 0.0

    # ── Auth-failure root-cause detection ─────────────────────────────────────
    auth_login_failed = False
    if auth:
        total = _safe_int(auth.get("Request Count"))
        fails = _safe_int(auth.get("Failure Count"))
        auth_login_failed = total > 0 and fails == total

    # ── Verdict line ──────────────────────────────────────────────────────────
    print()
    print(_THIN)

    if passed:
        detail = f"{overall_rps:.1f} RPS, {overall_fail_pct:.1f}% failures"
        print(f"  ✅ Load test PASSED — {detail}")
        print(f"  Core endpoints responding under {_USERS} concurrent users")
    else:
        detail = (
            f"{overall_fail_pct:.1f}% failure rate "
            f"(threshold < {_MAX_FAIL_PCT:.0f}%)"
        )
        print(f"  ❌ Load test FAILED — {detail}")

    # ── Supplementary notes ───────────────────────────────────────────────────
    if health_fail_pct > 0:
        print(f"  ⚠️  /health failure rate: {health_fail_pct:.1f}%  (should be 0%)")

    if auth_login_failed:
        print()
        print("  ⚠️  Auth note: every /api/auth/login request returned an error.")
        print("      401 failures on auth-gated endpoints are a configuration")
        print("      issue, not application bugs.  Seed the test credential:")
        print("        python scripts/seed_test_user.py")

    print(_THIN)

    return passed


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    print()
    print(_SEP)
    print("  MarketPulse India — Load Test  (Locust)")
    print(f"  {_USERS} users · {_SPAWN_RATE}/s spawn · {_RUN_TIME} run · {_HOST}")
    print(_SEP)
    print()

    # ── 1. Verify backend is reachable ────────────────────────────────────────
    print("  Checking backend reachability…")
    if not _backend_reachable():
        print()
        print(f"  ❌  Backend not reachable at {_HOST}/health")
        print("      Start it first:  make dev   or   uvicorn backend.main:app --reload")
        print()
        sys.exit(1)

    print(f"  ✅  Backend reachable at {_HOST}")
    print()

    # ── 2. Run Locust ─────────────────────────────────────────────────────────
    print("  Starting Locust…")
    print()
    t0 = time.monotonic()
    exit_code = _run_locust()
    elapsed = time.monotonic() - t0

    print()
    print(f"  Locust finished in {elapsed:.1f}s  (exit code {exit_code})")
    print()

    # ── 3. Parse and print summary table ─────────────────────────────────────
    print(_SEP)
    print("  Load Test Results")
    print(_THIN)
    print()

    rows = _parse_csv_stats()
    _print_summary(rows)

    # ── 4. Verdict ────────────────────────────────────────────────────────────
    passed = _print_verdict(rows)

    print(_SEP)
    print()

    # ── 5. Exit code ──────────────────────────────────────────────────────────
    if exit_code != 0:
        print(f"  ⚠️  Locust process exited with code {exit_code} — check output above.")
        sys.exit(2)

    if not passed:
        sys.exit(3)


if __name__ == "__main__":
    main()
