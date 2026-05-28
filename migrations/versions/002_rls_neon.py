"""Row-Level Security for user-scoped and signal tables (Neon / Postgres).

Revision ID: 002
Revises: 001
Create Date: 2026-05-28

Enables RLS on:
  - signals            — read-all policy; write restricted to app role
  - watchlist_items    — users see only their own rows (app.current_user_id)
  - alert_preferences  — users see only their own rows (app.current_user_id)

The application sets the session variable before every user-scoped query:
    SET LOCAL app.current_user_id = '<uuid>';

The app DB role (``marketpulse_app``) is granted BYPASSRLS so it can perform
admin writes (migrations, Lambda jobs) without being blocked by user policies.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# ---------------------------------------------------------------------------
# Alembic identifiers
# ---------------------------------------------------------------------------
revision = "002"
down_revision = "001"
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None

_APP_ROLE = "marketpulse_app"


def _exec(sql: str) -> None:
    op.get_bind().execute(sa.text(sql))


def upgrade() -> None:
    # ── Ensure the app role exists (idempotent) ────────────────────────────── #
    _exec(f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_roles WHERE rolname = '{_APP_ROLE}'
            ) THEN
                CREATE ROLE {_APP_ROLE} LOGIN;
            END IF;
        END
        $$;
    """)

    # Grant schema + table permissions to the app role
    _exec(f"GRANT USAGE ON SCHEMA public TO {_APP_ROLE};")
    for tbl in (
        "signals", "watchlist_items", "alert_preferences",
        "indian_stocks", "users", "announcements",
        "analysis_sessions", "retrieval_logs",
    ):
        _exec(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {tbl} TO {_APP_ROLE};")

    # App role bypasses RLS so migrations and Lambda jobs are unaffected
    _exec(f"ALTER ROLE {_APP_ROLE} BYPASSRLS;")

    # ── signals: read-all policy, app role writes ──────────────────────────── #
    _exec("ALTER TABLE signals ENABLE ROW LEVEL SECURITY;")
    _exec("ALTER TABLE signals FORCE ROW LEVEL SECURITY;")
    _exec("""
        CREATE POLICY signals_read_all ON signals
            FOR SELECT
            USING (true);
    """)

    # ── watchlist_items: owner-only ────────────────────────────────────────── #
    _exec("ALTER TABLE watchlist_items ENABLE ROW LEVEL SECURITY;")
    _exec("ALTER TABLE watchlist_items FORCE ROW LEVEL SECURITY;")
    _exec("""
        CREATE POLICY watchlist_owner ON watchlist_items
            FOR ALL
            USING (
                user_id = NULLIF(
                    current_setting('app.current_user_id', true), ''
                )::uuid
            )
            WITH CHECK (
                user_id = NULLIF(
                    current_setting('app.current_user_id', true), ''
                )::uuid
            );
    """)

    # ── alert_preferences: owner-only ─────────────────────────────────────── #
    _exec("ALTER TABLE alert_preferences ENABLE ROW LEVEL SECURITY;")
    _exec("ALTER TABLE alert_preferences FORCE ROW LEVEL SECURITY;")
    _exec("""
        CREATE POLICY alert_prefs_owner ON alert_preferences
            FOR ALL
            USING (
                user_id = NULLIF(
                    current_setting('app.current_user_id', true), ''
                )::uuid
            )
            WITH CHECK (
                user_id = NULLIF(
                    current_setting('app.current_user_id', true), ''
                )::uuid
            );
    """)


def downgrade() -> None:
    _exec("DROP POLICY IF EXISTS signals_read_all ON signals;")
    _exec("DROP POLICY IF EXISTS watchlist_owner ON watchlist_items;")
    _exec("DROP POLICY IF EXISTS alert_prefs_owner ON alert_preferences;")

    for tbl in ("signals", "watchlist_items", "alert_preferences"):
        _exec(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY;")
