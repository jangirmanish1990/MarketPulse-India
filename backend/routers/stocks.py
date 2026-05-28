"""Stocks router — list, detail, and sector-comparison views."""

from __future__ import annotations

import asyncio
import hashlib
import threading
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agents.sector_graph import SECTOR_SYMBOLS, run_sector_analysis
from backend.auth import CurrentUser
from backend.config import IST, SEBI_DISCLAIMER
from backend.database import get_db
from backend.exceptions import StockNotFoundError
from backend.models import IndianStock, Signal
from backend.repositories import SignalRepo

router = APIRouter()

DB = Annotated[AsyncSession, Depends(get_db)]


# ---------------------------------------------------------------------------
# Response models — list / detail
# ---------------------------------------------------------------------------


class StockBrief(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    company_name: str
    sector: str | None
    bse_code: str | None
    is_nifty50: bool
    is_sensex30: bool
    market_cap_cr: float | None


class SignalBrief(BaseModel):
    model_config = ConfigDict(frozen=True)

    direction: str
    confidence: float
    target_inr: float | None
    upside_pct: float | None
    created_ist: str
    sebi_disclaimer: str


class StockDetail(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    company_name: str
    sector: str | None
    bse_code: str | None
    is_nifty50: bool
    is_sensex30: bool
    market_cap_cr: float | None
    latest_signal: SignalBrief | None


class StockListResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    stocks: list[StockBrief]
    total: int


# ---------------------------------------------------------------------------
# Response models — sector comparison
# ---------------------------------------------------------------------------


class PeerMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)

    pe_ratio: float
    market_cap_cr: float
    revenue_growth_pct: float
    pat_margin_pct: float
    roe_pct: float


class PeerLatestSignal(BaseModel):
    model_config = ConfigDict(frozen=True)

    direction: str
    confidence: float
    target_inr: float | None


class SectorPeer(BaseModel):
    model_config = ConfigDict(frozen=True)

    nse_symbol: str
    company_name: str
    sector: str
    latest_signal: PeerLatestSignal | None
    metrics: PeerMetrics
    rank: int
    is_sector_best: bool


class SectorComparisonResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    sector: str
    sector_index: str
    sector_index_change_pct: float | None
    peers: list[SectorPeer]
    sector_signal: str   # bullish | bearish | neutral
    fii_trend: str       # bullish | bearish | neutral
    sebi_disclaimer: str


# ---------------------------------------------------------------------------
# Sector static data
# ---------------------------------------------------------------------------

# Each entry: index name, peer symbols, and realistic metric ranges.
_SECTOR_CONFIG: dict[str, dict[str, object]] = {
    "IT": {
        "index": "Nifty IT",
        "symbols": ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM"],
        "pe_range": (20.0, 35.0),
        "revenue_growth_range": (5.0, 12.0),
        "pat_margin_range": (12.0, 22.0),
        "roe_range": (20.0, 55.0),
        "market_cap_range": (60_000.0, 1_000_000.0),
    },
    "Banking": {
        "index": "Nifty Bank",
        "symbols": ["HDFCBANK", "ICICIBANK", "KOTAKBANK", "AXISBANK", "SBIN"],
        "pe_range": (10.0, 20.0),
        "revenue_growth_range": (8.0, 15.0),
        "pat_margin_range": (20.0, 35.0),
        "roe_range": (12.0, 22.0),
        "market_cap_range": (80_000.0, 1_500_000.0),
    },
    "FMCG": {
        "index": "Nifty FMCG",
        "symbols": ["HINDUNILVR", "ITC", "NESTLEIND", "DABUR", "MARICO"],
        "pe_range": (40.0, 70.0),
        "revenue_growth_range": (3.0, 8.0),
        "pat_margin_range": (10.0, 22.0),
        "roe_range": (25.0, 70.0),
        "market_cap_range": (20_000.0, 650_000.0),
    },
    "Pharma": {
        "index": "Nifty Pharma",
        "symbols": ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "AUROPHARMA"],
        "pe_range": (25.0, 45.0),
        "revenue_growth_range": (8.0, 18.0),
        "pat_margin_range": (14.0, 26.0),
        "roe_range": (14.0, 28.0),
        "market_cap_range": (25_000.0, 400_000.0),
    },
    "Energy": {
        "index": "Nifty Energy",
        "symbols": ["RELIANCE", "ONGC", "NTPC", "POWERGRID", "COALINDIA"],
        "pe_range": (8.0, 15.0),
        "revenue_growth_range": (2.0, 10.0),
        "pat_margin_range": (6.0, 22.0),
        "roe_range": (10.0, 25.0),
        "market_cap_range": (60_000.0, 2_200_000.0),
    },
}

# Case-insensitive lookup: "it" → "IT", "banking" → "Banking", etc.
_SECTOR_ALIAS: dict[str, str] = {k.lower(): k for k in _SECTOR_CONFIG}

# Built-in company names so the endpoint never relies solely on the DB for metadata.
_PEER_COMPANY_NAMES: dict[str, str] = {
    # IT
    "TCS":       "Tata Consultancy Services Ltd",
    "INFY":      "Infosys Ltd",
    "WIPRO":     "Wipro Ltd",
    "HCLTECH":   "HCL Technologies Ltd",
    "TECHM":     "Tech Mahindra Ltd",
    # Banking
    "HDFCBANK":  "HDFC Bank Ltd",
    "ICICIBANK": "ICICI Bank Ltd",
    "KOTAKBANK": "Kotak Mahindra Bank Ltd",
    "AXISBANK":  "Axis Bank Ltd",
    "SBIN":      "State Bank of India",
    # FMCG
    "HINDUNILVR":"Hindustan Unilever Ltd",
    "ITC":       "ITC Ltd",
    "NESTLEIND": "Nestle India Ltd",
    "DABUR":     "Dabur India Ltd",
    "MARICO":    "Marico Ltd",
    # Pharma
    "SUNPHARMA": "Sun Pharmaceutical Industries Ltd",
    "DRREDDY":   "Dr Reddy's Laboratories Ltd",
    "CIPLA":     "Cipla Ltd",
    "DIVISLAB":  "Divi's Laboratories Ltd",
    "AUROPHARMA":"Aurobindo Pharma Ltd",
    # Energy
    "RELIANCE":  "Reliance Industries Ltd",
    "ONGC":      "Oil & Natural Gas Corporation Ltd",
    "NTPC":      "NTPC Ltd",
    "POWERGRID": "Power Grid Corporation of India Ltd",
    "COALINDIA": "Coal India Ltd",
}


# ---------------------------------------------------------------------------
# Sector helpers (pure, no I/O)
# ---------------------------------------------------------------------------


def _sym_hash(sym: str, salt: str = "") -> int:
    """Stable, process-seed-independent integer hash (MD5-based).

    Appending *salt* lets us derive independent values for different metrics
    from the same symbol without correlation.
    """
    key = f"{sym}:{salt}" if salt else sym
    return int(hashlib.md5(key.encode(), usedforsecurity=False).hexdigest(), 16)


def _mock_metric(sym: str, salt: str, lo: float, hi: float) -> float:
    """Return a deterministic float in [lo, hi] for *sym* with *salt*."""
    frac = (_sym_hash(sym, salt) % 10_000) / 10_000.0  # [0.000, 0.9999]
    return round(lo + frac * (hi - lo), 1)


def _normalize(values: list[float]) -> list[float]:
    """Min-max normalise *values* to [0, 1]; returns 0.5 for all-equal inputs."""
    lo, hi = min(values), max(values)
    if hi == lo:
        return [0.5] * len(values)
    span = hi - lo
    return [(v - lo) / span for v in values]


def _composite_score(rev_n: float, pat_n: float, roe_n: float) -> float:
    """Weighted composite: revenue_growth 35 % + pat_margin 35 % + roe 30 %."""
    return rev_n * 0.35 + pat_n * 0.35 + roe_n * 0.30


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/stocks", response_model=StockListResponse)
async def list_stocks(
    db: DB,
    current_user: CurrentUser,
    sector: Annotated[str | None, Query()] = None,
    nifty50_only: Annotated[bool, Query()] = False,
) -> StockListResponse:
    """Return all instruments in the database, with optional filters."""
    stmt = select(IndianStock).order_by(IndianStock.nse_symbol)
    if nifty50_only:
        stmt = stmt.where(IndianStock.is_nifty50.is_(True))
    if sector:
        stmt = stmt.where(IndianStock.sector == sector)

    result = await db.execute(stmt)
    stocks = list(result.scalars().all())

    return StockListResponse(
        stocks=[
            StockBrief(
                symbol=s.nse_symbol,
                company_name=s.company_name,
                sector=s.sector,
                bse_code=s.bse_code,
                is_nifty50=s.is_nifty50,
                is_sensex30=s.is_sensex30,
                market_cap_cr=s.market_cap_cr,
            )
            for s in stocks
        ],
        total=len(stocks),
    )


@router.get("/stocks/sectors/{sector_name}", response_model=SectorComparisonResponse)
async def get_sector_comparison(
    sector_name: str,
    db: DB,
    current_user: CurrentUser,
) -> SectorComparisonResponse:
    """Peer comparison for a named sector (IT / Banking / FMCG / Pharma / Energy).

    Fundamental metrics (P/E, revenue growth, PAT margin, RoE) are generated
    deterministically from a stable hash so values are identical across requests.
    The latest buy/sell/hold signal for each peer is read from the live DB.

    Ranking uses a composite score:
        revenue_growth (35%) + pat_margin (35%) + roe (30%)
    with each metric normalised 0–1 across the peer set before weighting.
    """
    # ── Resolve sector ───────────────────────────────────────────────────────
    sector_key = _SECTOR_ALIAS.get(sector_name.lower())
    if sector_key is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown sector '{sector_name}'. "
                f"Valid options: {', '.join(_SECTOR_CONFIG)}"
            ),
        )
    cfg = _SECTOR_CONFIG[sector_key]
    symbols: list[str] = list(cfg["symbols"])  # type: ignore[arg-type]

    # ── Fetch latest signal per peer (DB, best-effort) ───────────────────────
    sig_repo = SignalRepo(db)
    signals_map: dict[str, Signal] = {}
    for sym in symbols:
        rows = await sig_repo.get_by_symbol(sym, limit=1)
        if rows:
            signals_map[sym] = rows[0]

    # ── Generate deterministic mock metrics ──────────────────────────────────
    def _metrics(sym: str) -> PeerMetrics:
        return PeerMetrics(
            pe_ratio=_mock_metric(sym, "pe",   *cfg["pe_range"]),            # type: ignore[arg-type]
            market_cap_cr=_mock_metric(sym, "mcap", *cfg["market_cap_range"]),  # type: ignore[arg-type]
            revenue_growth_pct=_mock_metric(sym, "rev",  *cfg["revenue_growth_range"]),  # type: ignore[arg-type]
            pat_margin_pct=_mock_metric(sym, "pat",  *cfg["pat_margin_range"]),    # type: ignore[arg-type]
            roe_pct=_mock_metric(sym, "roe",  *cfg["roe_range"]),            # type: ignore[arg-type]
        )

    metrics_map: dict[str, PeerMetrics] = {sym: _metrics(sym) for sym in symbols}

    # ── Composite ranking ────────────────────────────────────────────────────
    rev_vals = [metrics_map[s].revenue_growth_pct for s in symbols]
    pat_vals = [metrics_map[s].pat_margin_pct      for s in symbols]
    roe_vals = [metrics_map[s].roe_pct             for s in symbols]

    rev_n = _normalize(rev_vals)
    pat_n = _normalize(pat_vals)
    roe_n = _normalize(roe_vals)

    raw_scores = [
        _composite_score(rev_n[i], pat_n[i], roe_n[i])
        for i in range(len(symbols))
    ]

    # sorted_indices[0] = index of the best-scoring stock
    sorted_indices = sorted(range(len(symbols)), key=lambda i: raw_scores[i], reverse=True)
    rank_of: dict[str, int] = {symbols[idx]: rank for rank, idx in enumerate(sorted_indices, 1)}

    # ── sector_signal ─────────────────────────────────────────────────────────
    directions = [signals_map[s].direction for s in symbols if s in signals_map]
    n_sigs = len(directions)
    buy_count  = directions.count("BUY")
    sell_count = directions.count("SELL")

    if n_sigs == 0:
        sector_signal = "neutral"
    elif buy_count > n_sigs // 2:
        sector_signal = "bullish"
    elif sell_count > n_sigs // 2:
        sector_signal = "bearish"
    else:
        sector_signal = "neutral"

    # ── fii_trend — deterministic mock, loosely correlated with sector_signal ─
    _fii_pool: dict[str, list[str]] = {
        "bullish": ["bullish", "bullish", "neutral"],
        "bearish": ["bearish", "bearish", "neutral"],
        "neutral": ["bullish", "neutral", "bearish"],
    }
    fii_trend = _fii_pool[sector_signal][_sym_hash(sector_key, "fii") % 3]

    # ── sector_index_change_pct — deterministic mock in [-2.50, +2.50] ───────
    _idx_h = _sym_hash(sector_key, "idx")
    sector_index_change = round(((_idx_h % 501) - 250) / 100.0, 2)

    # ── Assemble peers list ──────────────────────────────────────────────────
    peers: list[SectorPeer] = []
    for sym in symbols:
        sig = signals_map.get(sym)
        peer_signal: PeerLatestSignal | None = None
        if sig is not None:
            peer_signal = PeerLatestSignal(
                direction=sig.direction,
                confidence=sig.confidence,
                target_inr=sig.target_price_inr,
            )

        rank = rank_of[sym]
        peers.append(
            SectorPeer(
                nse_symbol=sym,
                company_name=_PEER_COMPANY_NAMES.get(sym, sym),
                sector=sector_key,
                latest_signal=peer_signal,
                metrics=metrics_map[sym],
                rank=rank,
                is_sector_best=(rank == 1),
            )
        )

    peers.sort(key=lambda p: p.rank)

    return SectorComparisonResponse(
        sector=sector_key,
        sector_index=str(cfg["index"]),
        sector_index_change_pct=sector_index_change,
        peers=peers,
        sector_signal=sector_signal,
        fii_trend=fii_trend,
        sebi_disclaimer=SEBI_DISCLAIMER,
    )


@router.post("/stocks/sectors/{sector_name}/analyze")
async def analyze_sector(
    sector_name: str,
    db: DB,  # noqa: ARG001  — kept for auth + future DB writes
    current_user: CurrentUser,  # noqa: ARG001  — auth guard
) -> dict[str, Any]:
    """Run the live sector-analysis graph for *sector_name*.

    Fans out over all 5 constituent stocks in parallel (LangGraph Send API),
    fetches yfinance fundamentals for each, then ranks them by a weighted
    composite score (revenue scale 25%, PAT margin 30%, ROE 30%, PE⁻¹ 15%).

    Returns
    -------
    sector          — canonical sector key (e.g. ``"IT"``)
    session_id      — UUID for this run (use in WebSocket trace if needed)
    sector_signal   — ``"bullish"`` | ``"neutral"`` | ``"bearish"``
    sector_winner   — NSE symbol of the top-ranked stock
    fii_trend       — FII flow direction (passed through from graph)
    peers           — list of PeerResult dicts, sorted by rank
    total_analyzed  — number of peers successfully analyzed (no error)
    sebi_disclaimer — mandatory disclaimer string
    """
    # ── Validate sector ──────────────────────────────────────────────────────
    sector_key: str | None = None
    for k in SECTOR_SYMBOLS:
        if k.lower() == sector_name.lower():
            sector_key = k
            break

    if sector_key is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown sector '{sector_name}'. "
                f"Valid options: {', '.join(sorted(SECTOR_SYMBOLS))}"
            ),
        )

    session_id = str(uuid.uuid4())

    # ── Run sector graph in a dedicated thread + event loop ──────────────────
    # FastAPI's own event loop must not be blocked; spin a thread with its own
    # loop so the async LangGraph graph runs cleanly on all platforms.
    result_container: dict[str, Any] = {}
    error_container: dict[str, str] = {}

    def _run() -> None:
        if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            data = loop.run_until_complete(
                run_sector_analysis(sector_key, session_id)  # type: ignore[arg-type]
            )
            result_container["data"] = data
        except Exception as exc:
            error_container["error"] = str(exc)
        finally:
            loop.close()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=90)  # 90 s — 5 stocks × ~15 s each, with margin

    if thread.is_alive():
        raise HTTPException(status_code=504, detail="Sector analysis timed out")
    if "error" in error_container:
        raise HTTPException(status_code=500, detail=error_container["error"])

    graph_result: dict[str, Any] = result_container["data"]

    # ── Shape the response ───────────────────────────────────────────────────
    peers: list[dict[str, Any]] = [
        dict(p) for p in graph_result.get("sector_ranking", [])
    ]
    total_analyzed = sum(1 for p in peers if not p.get("error"))

    return {
        "sector": sector_key,
        "session_id": session_id,
        "sector_signal": graph_result.get("sector_signal", "neutral"),
        "sector_winner": graph_result.get("sector_winner", ""),
        "fii_trend": graph_result.get("fii_trend", "neutral"),
        "peers": peers,
        "total_analyzed": total_analyzed,
        "sebi_disclaimer": SEBI_DISCLAIMER,
    }


@router.get("/stocks/{nse_symbol}", response_model=StockDetail)
async def get_stock(
    nse_symbol: str,
    db: DB,
    current_user: CurrentUser,
) -> StockDetail:
    """Return details for a single stock plus its latest signal if available."""
    nse_symbol = nse_symbol.upper()

    result = await db.execute(select(IndianStock).where(IndianStock.nse_symbol == nse_symbol))
    stock = result.scalar_one_or_none()
    if stock is None:
        raise StockNotFoundError(nse_symbol)

    signals: list[Signal] = list(await SignalRepo(db).get_by_symbol(nse_symbol, limit=1))
    latest: SignalBrief | None = None
    if signals:
        sig = signals[0]
        latest = SignalBrief(
            direction=sig.direction,
            confidence=sig.confidence,
            target_inr=sig.target_price_inr,
            upside_pct=sig.upside_pct,
            created_ist=sig.created_at.astimezone(IST).isoformat(),
            sebi_disclaimer=SEBI_DISCLAIMER,
        )

    return StockDetail(
        symbol=stock.nse_symbol,
        company_name=stock.company_name,
        sector=stock.sector,
        bse_code=stock.bse_code,
        is_nifty50=stock.is_nifty50,
        is_sensex30=stock.is_sensex30,
        market_cap_cr=stock.market_cap_cr,
        latest_signal=latest,
    )
