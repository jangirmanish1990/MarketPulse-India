"""IndiaMarketState — the single canonical LangGraph state for MarketPulse India.

Every node reads from and writes into this TypedDict. All fields are present
on every state object; nullable fields are typed `X | None` and start as None.
"""

from __future__ import annotations

from typing import Literal, TypedDict


class IndiaMarketState(TypedDict):
    # ── Input ──────────────────────────────────────────────────────────────
    nse_symbol: str
    bse_code: str
    exchange: Literal["NSE", "BSE", "BOTH"]
    announcement_type: Literal[
        "quarterly_results", "board_meeting",
        "insider_trade", "shareholding", "other"
    ]
    announcement_raw: str
    s3_key: str
    thread_id: str
    session_id: str

    # ── Fetched Market Data ────────────────────────────────────────────────
    price_history: dict
    financials: dict
    live_quote: dict
    index_data: dict
    usd_inr: float

    # ── Parsed Announcement ────────────────────────────────────────────────
    parsed_quarterly: dict | None
    parsed_board: dict | None
    parsed_insider: dict | None
    parsed_shp: dict | None

    # ── Concall Analysis ───────────────────────────────────────────────────
    concall_available: bool
    concall_tone: Literal["optimistic", "cautious", "defensive", "mixed"] | None
    concall_guidance_cr: float | None
    concall_signal_adjustment: Literal["upgrade", "maintain", "downgrade"] | None

    # ── India Market Context ───────────────────────────────────────────────
    nifty_value: float
    nifty_change_pct: float
    sector_index_change_pct: float
    fii_net_flow_cr: float
    fii_sentiment: Literal["strong_buyer", "buyer", "neutral", "seller", "strong_seller"]
    usd_inr_context: str
    market_status: Literal["PRE_MARKET", "OPEN", "POST_MARKET", "CLOSED", "WEEKEND"]

    # ── RAG ────────────────────────────────────────────────────────────────
    retrieved_docs: list
    doc_grades: list
    used_web_fallback: bool

    # ── Institutional Intelligence ─────────────────────────────────────────
    promoter_pct: float | None
    promoter_trend: Literal["increasing", "stable", "decreasing"] | None
    promoter_pledging_pct: float | None
    promoter_pledging_risk: Literal["high", "medium", "low", "none"] | None
    fii_ownership_trend: str | None

    # ── Output ─────────────────────────────────────────────────────────────
    analysis_summary: str | None
    key_positives: list | None
    key_risks: list | None
    quarter_verdict: Literal["beat", "in-line", "miss"] | None
    sector_outlook: Literal["bullish", "neutral", "bearish"] | None
    signal_direction: Literal["BUY", "HOLD", "SELL"] | None
    confidence: float | None
    current_price_inr: float | None
    target_price_inr: float | None
    upside_pct: float | None
    time_horizon_days: int | None
    rationale: str | None
    sebi_disclaimer: str

    # ── Meta ───────────────────────────────────────────────────────────────
    error: str | None
    retry_count: int
    node_timings: dict


__all__ = ["IndiaMarketState"]
