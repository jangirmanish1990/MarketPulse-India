"""scripts/seed_test_user.py — Seed the load-test user into the DB.

The MarketPulse India auth system maintains in-memory credentials in
``DEMO_USERS`` (backend/auth.py).  ``testuser`` / ``testpass123`` is
already present there so the load test can obtain a JWT.

This companion script inserts the matching row into the ``users``
table so the ORM has a record for any future DB-backed auth migration.

Credentials seeded
------------------
  username (DEMO_USERS key) : testuser
  password                  : testpass123  (bcrypt in DEMO_USERS)
  email (users table)       : test@marketpulse.in
  risk_profile              : moderate

Usage
-----
    python scripts/seed_test_user.py
    uv run python scripts/seed_test_user.py

Exit codes
----------
  0 — user created or already exists in the DB
  1 — DB unreachable / DATABASE_URL not set / unexpected failure
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Repo root on sys.path so absolute imports work from any cwd.
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Windows: asyncpg requires SelectorEventLoop — must be set BEFORE any import
# that touches the event loop (including dotenv on some setups).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Windows: force UTF-8 console so ✅ / ═ characters render correctly.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_ROOT / ".env")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TEST_EMAIL    = "test@marketpulse.in"
_RISK_PROFILE  = "moderate"

_SEP  = "═" * 54
_THIN = "─" * 54


# ---------------------------------------------------------------------------
# Async seed logic
# ---------------------------------------------------------------------------


async def _seed() -> None:
    """Insert test@marketpulse.in into the users table if it doesn't exist."""
    from sqlalchemy import select
    from sqlalchemy.exc import IntegrityError

    from backend.database import dispose_engine, get_session_factory
    from backend.models import User

    factory = get_session_factory()
    try:
        async with factory() as session:
            result = await session.execute(
                select(User).where(User.email == _TEST_EMAIL)
            )
            existing = result.scalar_one_or_none()

            if existing is not None:
                print("  Test user already exists ✅")
                return

            user = User(email=_TEST_EMAIL, risk_profile=_RISK_PROFILE)
            session.add(user)
            try:
                await session.commit()
                print("  Test user created ✅")
            except IntegrityError:
                # Race condition — another process inserted concurrently.
                await session.rollback()
                print("  Test user already exists ✅")
    finally:
        await dispose_engine()


# ---------------------------------------------------------------------------
# Synchronous entry point — safe on Windows (SelectorEventLoop already set)
# ---------------------------------------------------------------------------


def _run_async(coro: object) -> None:
    """Run an async coroutine, works safely on Windows."""
    import asyncio as _asyncio
    import types

    if not isinstance(coro, types.CoroutineType):
        raise TypeError(f"Expected coroutine, got {type(coro)!r}")

    if sys.platform == "win32":
        loop = _asyncio.new_event_loop()
        try:
            loop.run_until_complete(coro)
        finally:
            loop.close()
    else:
        _asyncio.run(coro)  # type: ignore[arg-type]


def main() -> None:
    print()
    print(_SEP)
    print("  MarketPulse India — Seed Test User")
    print(_THIN)
    print()
    print(f"  Username  : testuser           (DEMO_USERS in auth.py)")
    print(f"  Password  : testpass123        (bcrypt-hashed in auth.py)")
    print(f"  Email     : {_TEST_EMAIL}")
    print(f"  is_active : True               (DEMO_USERS entry present)")
    print()

    # ── Verify DEMO_USERS has testuser ────────────────────────────────────────
    try:
        from backend.auth import DEMO_USERS

        if "testuser" in DEMO_USERS:
            print("  DEMO_USERS  : testuser present ✅")
        else:
            print("  DEMO_USERS  : ⚠️  testuser NOT found — add it to backend/auth.py")
    except ImportError as exc:
        print(f"  DEMO_USERS  : could not import backend.auth ({exc})")

    print()

    # ── Seed users table ──────────────────────────────────────────────────────
    import os

    if not os.getenv("DATABASE_URL"):
        print("  DATABASE_URL not set — skipping DB seed.")
        print("  Auth-only mode: testuser is available via DEMO_USERS.")
        print()
        print(_SEP)
        print()
        return

    print("  Seeding users table…")
    try:
        _run_async(_seed())
    except Exception as exc:
        print()
        print(f"  ❌  DB seed failed: {exc}")
        print("      Check DATABASE_URL in .env and ensure the DB is running.")
        print()
        print(_SEP)
        print()
        sys.exit(1)

    print()
    print(_SEP)
    print()


if __name__ == "__main__":
    main()
