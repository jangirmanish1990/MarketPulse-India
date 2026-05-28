"""scripts/check_sebi.py — SEBI disclaimer compliance audit.

Checks every signal-bearing surface for the required disclaimer.
Exits 1 if any non-DB check fails.

Usage:
    python scripts/check_sebi.py
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path

# Windows: force ProactorEventLoop so asyncpg works
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Windows: force UTF-8 so Unicode characters don't crash on cp1252
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_SEP  = "─" * 50
_SEBI_KEYWORDS = re.compile(
    r"SEBI|educational|not investment|not a SEBI|not SEBI",
    re.IGNORECASE,
)

passed: list[str] = []
failed: list[str] = []


def _ok(label: str) -> None:
    passed.append(label)
    print(f"  {label:<44} ✅")


def _fail(label: str, reason: str = "") -> None:
    failed.append(label)
    detail = f"  — {reason}" if reason else ""
    print(f"  {label:<44} ❌{detail}")


# ── Check 1: Alert template formatters ────────────────────────────────────────

def check_alert_templates() -> None:
    disp = ROOT / "backend" / "alerts" / "dispatcher.py"
    if not disp.exists():
        _fail("Alert templates (dispatcher.py)", "file not found")
        return

    src = disp.read_text(encoding="utf-8")

    # Extract each formatter's body
    formatters = {
        "format_whatsapp": re.search(
            r"def format_whatsapp.*?(?=\ndef |\Z)", src, re.DOTALL),
        "format_telegram": re.search(
            r"def format_telegram.*?(?=\ndef |\Z)", src, re.DOTALL),
        "format_sms": re.search(
            r"def format_sms.*?(?=\ndef |\Z)", src, re.DOTALL),
    }

    hits = 0
    for name, m in formatters.items():
        if m and _SEBI_KEYWORDS.search(m.group()):
            hits += 1

    label = f"Alert templates ({len(formatters)} checked)"
    if hits == len(formatters):
        _ok(label + f" : {hits}/{len(formatters)}")
    else:
        _fail(label, f"only {hits}/{len(formatters)} contain SEBI text")


# ── Check 2: Frontend components ──────────────────────────────────────────────

def check_frontend() -> None:
    src_dir = ROOT / "frontend" / "src"
    if not src_dir.exists():
        _fail("Frontend component", "frontend/src not found")
        return

    found_in: list[str] = []
    for ext in ("*.jsx", "*.tsx", "*.js", "*.ts"):
        for fp in src_dir.rglob(ext):
            if _SEBI_KEYWORDS.search(fp.read_text(encoding="utf-8", errors="replace")):
                found_in.append(fp.name)

    if found_in:
        _ok(f"Frontend component           : found in {', '.join(found_in[:3])}")
    else:
        _fail("Frontend component", "no JSX/TSX file contains SEBI text")


# ── Check 3: API response schema ──────────────────────────────────────────────

def check_api_schema() -> None:
    routers_dir = ROOT / "backend" / "routers"
    if not routers_dir.exists():
        _fail("API response schema", "backend/routers not found")
        return

    field_pattern = re.compile(r"sebi_disclaimer", re.IGNORECASE)
    found_in: list[str] = []
    for fp in routers_dir.glob("*.py"):
        src = fp.read_text(encoding="utf-8", errors="replace")
        if field_pattern.search(src):
            found_in.append(fp.name)

    if found_in:
        _ok(f"API response schema          : field in {', '.join(found_in)}")
    else:
        _fail("API response schema", "sebi_disclaimer field not found in any router")


# ── Check 4: DB signals (last 5) ─────────────────────────────────────────────

async def _query_db_signals() -> tuple[int, int] | None:
    """Return (checked, with_disclaimer) or None if DB unreachable."""
    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        return None
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
        db_url = os.getenv("DATABASE_URL", "")
        if not db_url:
            return None

        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine(db_url, connect_args={"ssl": "require"} if "neon" in db_url else {})
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT sebi_disclaimer FROM signals ORDER BY created_at DESC LIMIT 5")
            )
            rows = result.fetchall()
            if not rows:
                return (0, 0)
            with_disclaimer = sum(
                1 for r in rows
                if r[0] and _SEBI_KEYWORDS.search(str(r[0]))
            )
            return (len(rows), with_disclaimer)
    except Exception as exc:
        print(f"    (DB query error: {type(exc).__name__}: {exc})")
        return None


def check_db_signals() -> None:
    try:
        result = asyncio.run(_query_db_signals())
    except Exception:
        result = None

    if result is None:
        print(f"  {'DB signals (last 5)':<44} ⚠️  skipped (DB unreachable)")
        return

    checked, ok = result
    if checked == 0:
        print(f"  {'DB signals (last 5)':<44} ⚠️  skipped (no signals in DB yet)")
        return

    label = f"DB signals (last {checked})"
    if ok == checked:
        _ok(f"{label:<44} : {ok}/{checked}")
    else:
        _fail(label, f"only {ok}/{checked} rows carry disclaimer")


# ── Report ────────────────────────────────────────────────────────────────────

def main() -> None:
    print()
    print("  SEBI Compliance Audit")
    print(_SEP)

    check_alert_templates()
    check_frontend()
    check_api_schema()
    check_db_signals()

    print(_SEP)

    if not failed:
        print("  SEBI compliance: PASSED ✅")
        print()
        sys.exit(0)
    else:
        print(f"  SEBI compliance: FAILED ❌  ({len(failed)} check(s) failed)")
        for f in failed:
            print(f"    — {f}")
        print()
        sys.exit(1)


if __name__ == "__main__":
    main()
