"""Initial schema: 8 tables for MarketPulse India.

Revision ID: 001
Revises:
Create Date: 2026-05-19

Creates: indian_stocks, users, watchlist_items, announcements,
analysis_sessions, signals, retrieval_logs, alert_preferences.

All timestamps are TIMESTAMPTZ (Postgres normalizes to UTC). Primary keys
are UUID v4. Single-column indexes are declared inline.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# ---------------------------------------------------------------------------
# Alembic identifiers
# ---------------------------------------------------------------------------
revision = "001"
down_revision: str | None = None
branch_labels: tuple[str, ...] | None = None
depends_on: tuple[str, ...] | None = None


SEBI_DISCLAIMER_DEFAULT = "Not a SEBI registered advisor. For educational use only."


def upgrade() -> None:
    # ----- indian_stocks -----
    op.create_table(
        "indian_stocks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("nse_symbol", sa.String(length=20), nullable=False),
        sa.Column("bse_code", sa.String(length=10), nullable=True),
        sa.Column("company_name", sa.String(length=100), nullable=False),
        sa.Column("sector", sa.String(length=50), nullable=True),
        sa.Column("market_cap_cr", sa.Float(), nullable=True),
        sa.Column(
            "is_nifty50",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_sensex30",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("nse_symbol", name="uq_indian_stocks_nse_symbol"),
    )
    op.create_index("ix_indian_stocks_nse_symbol", "indian_stocks", ["nse_symbol"], unique=False)

    # ----- users -----
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone_in", sa.String(length=15), nullable=True),
        sa.Column("telegram_id", sa.String(length=50), nullable=True),
        sa.Column(
            "risk_profile",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'moderate'"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    # ----- watchlist_items -----
    op.create_table(
        "watchlist_items",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "nse_symbol",
            sa.String(length=20),
            sa.ForeignKey("indian_stocks.nse_symbol", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "added_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "alert_threshold",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.75"),
        ),
    )

    # ----- announcements -----
    op.create_table(
        "announcements",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("nse_symbol", sa.String(length=20), nullable=False),
        sa.Column("exchange", sa.String(length=5), nullable=False),
        sa.Column("announcement_type", sa.String(length=50), nullable=True),
        sa.Column("raw_content", sa.Text(), nullable=True),
        sa.Column("s3_key", sa.String(length=200), nullable=True),
        sa.Column("published_ist", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "processed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_announcements_nse_symbol", "announcements", ["nse_symbol"], unique=False)
    op.create_index(
        "ix_announcements_published_ist",
        "announcements",
        ["published_ist"],
        unique=False,
    )

    # ----- analysis_sessions -----
    op.create_table(
        "analysis_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("thread_id", sa.String(length=100), nullable=False),
        sa.Column("nse_symbol", sa.String(length=20), nullable=False),
        sa.Column("trigger_type", sa.String(length=50), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("thread_id", name="uq_analysis_sessions_thread_id"),
    )
    op.create_index(
        "ix_analysis_sessions_nse_symbol",
        "analysis_sessions",
        ["nse_symbol"],
        unique=False,
    )

    # ----- signals -----
    op.create_table(
        "signals",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("nse_symbol", sa.String(length=20), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("current_price_inr", sa.Float(), nullable=True),
        sa.Column("target_price_inr", sa.Float(), nullable=True),
        sa.Column("upside_pct", sa.Float(), nullable=True),
        sa.Column("time_horizon_days", sa.Integer(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column(
            "sebi_disclaimer",
            sa.Text(),
            nullable=False,
            server_default=sa.text(f"'{SEBI_DISCLAIMER_DEFAULT}'"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_signals_nse_symbol", "signals", ["nse_symbol"], unique=False)
    op.create_index("ix_signals_created_at", "signals", ["created_at"], unique=False)

    # ----- retrieval_logs -----
    op.create_table(
        "retrieval_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("query", sa.Text(), nullable=True),
        sa.Column(
            "docs_retrieved",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "docs_graded_relevant",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "used_web_fallback",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ----- alert_preferences -----
    op.create_table(
        "alert_preferences",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "min_confidence",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0.75"),
        ),
        sa.Column("sectors", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column(
            "directions",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY['BUY']::text[]"),
        ),
        sa.Column(
            "channels",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY['email']::text[]"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    # Drop in reverse order of creation to respect FKs.
    op.drop_table("alert_preferences")
    op.drop_table("retrieval_logs")
    op.drop_index("ix_signals_created_at", table_name="signals")
    op.drop_index("ix_signals_nse_symbol", table_name="signals")
    op.drop_table("signals")
    op.drop_index("ix_analysis_sessions_nse_symbol", table_name="analysis_sessions")
    op.drop_table("analysis_sessions")
    op.drop_index("ix_announcements_published_ist", table_name="announcements")
    op.drop_index("ix_announcements_nse_symbol", table_name="announcements")
    op.drop_table("announcements")
    op.drop_table("watchlist_items")
    op.drop_table("users")
    op.drop_index("ix_indian_stocks_nse_symbol", table_name="indian_stocks")
    op.drop_table("indian_stocks")
