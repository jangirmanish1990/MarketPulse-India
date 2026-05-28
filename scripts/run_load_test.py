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

Exit codes
----------
  0 — test completed (non-zero failure count is reported but doesn't gate)
  1 — backend unreachable (test not started)
  2 — locust subprocess exited with non-zero status
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
_REPORT_CSV  = _ROOT / "tests" / "load" / "stats"          # locust appends _stats.csv etc.
_HOST        = "http://localhost:8000"
_USERS       = 20
_SPAWN_RATE  = 4
_RUN_TIME    = "30s"

_SEP  = "═" * 66
_THIN = "─" * 66


# ---------------------------------------------------------------------------
# Helpers
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


def _run_locust() -> int:
    """Execute locust as a subprocess and return its exit code."""
    # Ensure output directory exists.
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
        "--only-summary",          # suppress per-second output noise
    ]

    print(f"  Running: {' '.join(cmd[2:])}")   # omit 'python -m' prefix
    print()

    result = subprocess.run(cmd, cwd=_ROOT)
    return result.returncode


def _parse_csv_stats() -> list[dict[str, str]]:
    """Read tests/load/stats_stats.csv and return rows as list-of-dicts.

    Locust 2.x names the file  <prefix>_stats.csv  where <prefix> is the
    --csv argument.  We fall back to any *_stats.csv glob if the canonical
    name is missing.
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


def _print_summary(rows: list[dict[str, str]]) -> None:
    """Print the formatted Endpoint / RPS / P95 / Fails table."""
    if not rows:
        print("  ⚠️  No CSV stats found — check tests/load/ for report files.")
        return

    # Column widths
    W_EP   = 38
    W_RPS  = 8
    W_P95  = 8
    W_FAIL = 7

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
    any_fail = False

    for r in rows:
        name = r.get("Name", "").strip()
        if name.lower() in {"aggregated", ""}:
            aggregated_row = r
            continue

        # Locust CSV columns (2.x):
        #   "Requests/s", "95%", "Failure Count"
        try:
            rps  = f"{float(r.get('Requests/s', 0)):.1f}"
        except ValueError:
            rps = "—"
        try:
            p95  = f"{int(float(r.get('95%', 0)))}ms"
        except ValueError:
            p95 = "—"
        try:
            fails = str(int(r.get("Failure Count", 0)))
        except ValueError:
            fails = "—"

        if fails not in ("0", "—"):
            any_fail = True

        print(_row(name, rps, p95, fails))

    # Aggregated row always printed last, separated by a thin rule.
    if aggregated_row:
        print(f"  ├{'─'*W_EP}┼{'─'*W_RPS}┼{'─'*W_P95}┼{'─'*W_FAIL}┤")
        try:
            rps  = f"{float(aggregated_row.get('Requests/s', 0)):.1f}"
        except ValueError:
            rps = "—"
        try:
            p95  = f"{int(float(aggregated_row.get('95%', 0)))}ms"
        except ValueError:
            p95 = "—"
        try:
            fails = str(int(aggregated_row.get("Failure Count", 0)))
        except ValueError:
            fails = "—"
        print(_row("Aggregated", rps, p95, fails))

    print(_footer())
    print()

    if any_fail:
        print("  ⚠️  Some endpoints reported failures — see report.html for details.")
    else:
        print("  ✅  Zero failures across all endpoints.")

    print()

    try:
        rel = _REPORT_HTML.relative_to(_ROOT)
    except ValueError:
        rel = _REPORT_HTML
    print(f"  HTML report → {rel}")


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

    # ── 3. Parse and print summary ────────────────────────────────────────────
    print(_SEP)
    print("  Load Test Results")
    print(_THIN)
    print()

    rows = _parse_csv_stats()
    _print_summary(rows)

    print(_SEP)
    print()

    if exit_code != 0:
        print(f"  ⚠️  Locust exited with code {exit_code} — check output above.")
        sys.exit(2)


if __name__ == "__main__":
    main()
