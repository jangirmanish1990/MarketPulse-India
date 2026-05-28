import { useState, useEffect, useMemo } from "react"
import axios from "axios"
import { useAuth } from "../context/AuthContext"

const API = ""

const SECTORS = ["IT", "Banking", "FMCG", "Pharma", "Energy"]

// ─── Sector constituent symbols (mirrors agents/sector_graph.py) ───────────

const SECTOR_SYMBOLS = {
  IT:      ["TCS", "INFY", "WIPRO", "HCLTECH", "TECHM"],
  Banking: ["HDFCBANK", "ICICIBANK", "KOTAKBANK", "AXISBANK", "SBIN"],
  FMCG:    ["HINDUNILVR", "ITC", "NESTLEIND", "DABUR", "MARICO"],
  Pharma:  ["SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "AUROPHARMA"],
  Energy:  ["RELIANCE", "ONGC", "NTPC", "POWERGRID", "COALINDIA"],
}

// Static index names used in the summary bar (POST endpoint doesn't return them)
const SECTOR_INDEX_MAP = {
  IT:      "Nifty IT",
  Banking: "Nifty Bank",
  FMCG:    "Nifty FMCG",
  Pharma:  "Nifty Pharma",
  Energy:  "Nifty Energy",
}

// ─── Number formatters ─────────────────────────────────────────────────────

function numFmt(n, dec = 1) {
  if (n == null) return "—"
  return Number(n).toLocaleString("en-IN", {
    minimumFractionDigits: dec,
    maximumFractionDigits: dec,
  })
}

function pctFmt(n, showSign = false) {
  if (n == null) return "—"
  const v = Number(n)
  const sign = showSign && v > 0 ? "+" : ""
  return `${sign}${v.toFixed(1)}%`
}

// ─── Compute composite scores client-side (mirrors backend formula exactly) ─
// revenue_growth × 0.35 + pat_margin × 0.35 + roe × 0.30
// Each metric is min-max normalised across the peer set before weighting.

function minMaxNorm(values) {
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  if (hi === lo) return values.map(() => 0.5)
  return values.map((v) => (v - lo) / (hi - lo))
}

function computeScores(peers) {
  if (!peers.length) return []
  const rev = peers.map((p) => p.metrics?.revenue_growth_pct ?? 0)
  const pat = peers.map((p) => p.metrics?.pat_margin_pct     ?? 0)
  const roe = peers.map((p) => p.metrics?.roe_pct            ?? 0)
  const rN  = minMaxNorm(rev)
  const pN  = minMaxNorm(pat)
  const oN  = minMaxNorm(roe)
  return peers.map((_, i) => rN[i] * 0.35 + pN[i] * 0.35 + oN[i] * 0.30)
}

// ─── Normalise POST /sector/analyze response → table-ready shape ──────────
// POST /api/sector/analyze returns flat PeerResult dicts in `sector_ranking`.
// The existing table components expect nested {metrics, latest_signal}.
// This adapter shapes the response so no table component needs changing.

function normalizeLiveData(postData) {
  return {
    sector:                  postData.sector,
    // POST doesn't return sector_index/change — fill from static map
    sector_index:            SECTOR_INDEX_MAP[postData.sector] ?? postData.sector,
    sector_index_change_pct: null,
    sector_signal:           postData.sector_signal,
    fii_trend:               postData.fii_trend,
    sebi_disclaimer:         postData.sebi_disclaimer,
    // Accept sector_ranking (new endpoint) or peers (legacy) interchangeably
    peers: (postData.sector_ranking ?? postData.peers ?? []).map((p) => ({
      nse_symbol:      p.nse_symbol,
      company_name:    p.company_name,
      sector:          p.sector,
      rank:            p.rank,
      is_sector_best:  p.is_sector_best,
      // Keep composite_score from the graph so the scores useMemo can use it
      // directly rather than re-computing from incomplete metrics.
      _composite_score: p.composite_score,
      latest_signal:
        p.signal_direction && p.signal_direction !== "—" && p.signal_direction !== ""
          ? {
              direction:  p.signal_direction,
              confidence: p.confidence,
              target_inr: p.target_price_inr,
            }
          : null,
      metrics: {
        pe_ratio:           p.pe_ratio        ?? 0,
        market_cap_cr:      null,
        // yfinance quick-fetch doesn't return revenue_growth — show "—" in table
        revenue_growth_pct: null,
        pat_margin_pct:     p.pat_margin_pct  ?? 0,
        roe_pct:            p.roe_pct         ?? 0,
      },
    })),
  }
}

// ─── Sub-components ────────────────────────────────────────────────────────

// Section 1 — tab strip (accepts children so the Analyse button can sit inline)
function SectorTabs({ active, onChange, children }) {
  return (
    <div className="flex items-center border-b border-mp-border flex-shrink-0">
      {SECTORS.map((s) => (
        <button
          key={s}
          onClick={() => onChange(s)}
          className={`px-4 py-2.5 text-xs font-mono font-bold
                     tracking-wider transition-all border-b-2 -mb-px
                     ${active === s
                       ? "border-mp-saffron text-mp-saffron"
                       : "border-transparent text-mp-muted hover:text-mp-text"}`}
        >
          {s}
        </button>
      ))}
      {children}
    </div>
  )
}

// Section 2 helpers — sector signal badge + FII indicator
function SectorSignalBadge({ signal }) {
  const MAP = {
    bullish: { color: "#00E676", label: "BULLISH" },
    bearish: { color: "#FF3D57", label: "BEARISH" },
    neutral: { color: "#FFB800", label: "NEUTRAL" },
  }
  const { color, label } = MAP[signal] ?? MAP.neutral
  return (
    <span
      className="font-mono text-[10px] font-bold px-2 py-0.5 rounded
                 tracking-wider uppercase"
      style={{
        color,
        backgroundColor: `${color}1A`,
        border: `1px solid ${color}40`,
      }}
    >
      {label}
    </span>
  )
}

function FIITrend({ trend }) {
  const MAP = {
    bullish: { arrow: "↑", color: "#00E676", label: "Bullish" },
    bearish: { arrow: "↓", color: "#FF3D57", label: "Bearish" },
    neutral: { arrow: "→", color: "#4A5A78", label: "Neutral" },
  }
  const { arrow, color, label } = MAP[trend] ?? MAP.neutral
  return (
    <span className="font-mono text-xs font-bold" style={{ color }}>
      {arrow} FII {label}
    </span>
  )
}

// Section 2 — summary bar
function SectorSummaryBar({ data }) {
  const chg = data.sector_index_change_pct
  const chgColor = chg == null ? "#4A5A78" : chg >= 0 ? "#00E676" : "#FF3D57"
  const chgSign  = chg != null && chg > 0 ? "+" : ""

  return (
    <div
      className="mp-card flex flex-wrap items-center gap-x-5 gap-y-2 py-3"
    >
      {/* Index name */}
      <div className="flex flex-col gap-0.5">
        <span className="font-mono text-[10px] text-mp-dim tracking-wider uppercase">
          Index
        </span>
        <span className="font-mono text-sm font-bold text-mp-text">
          {data.sector_index}
        </span>
      </div>

      <span className="text-mp-dim select-none hidden sm:block">·</span>

      {/* Index change */}
      <div className="flex flex-col gap-0.5">
        <span className="font-mono text-[10px] text-mp-dim tracking-wider uppercase">
          Change
        </span>
        <span className="font-mono text-sm font-bold" style={{ color: chgColor }}>
          {chg != null ? `${chgSign}${chg.toFixed(2)}%` : "—"}
        </span>
      </div>

      <span className="text-mp-dim select-none hidden sm:block">·</span>

      {/* Sector signal */}
      <div className="flex flex-col gap-0.5">
        <span className="font-mono text-[10px] text-mp-dim tracking-wider uppercase">
          Sector Signal
        </span>
        <SectorSignalBadge signal={data.sector_signal} />
      </div>

      <span className="text-mp-dim select-none hidden sm:block">·</span>

      {/* FII trend */}
      <div className="flex flex-col gap-0.5">
        <span className="font-mono text-[10px] text-mp-dim tracking-wider uppercase">
          FII Trend
        </span>
        <FIITrend trend={data.fii_trend} />
      </div>
    </div>
  )
}

// Section 3 helpers — signal badge, score bar, PE colour

function SignalBadge({ direction }) {
  if (!direction) {
    return <span className="font-mono text-xs text-mp-dim">—</span>
  }
  const cls = {
    BUY:  "mp-badge mp-badge-buy",
    SELL: "mp-badge mp-badge-sell",
    HOLD: "mp-badge mp-badge-hold",
  }
  return <span className={cls[direction] ?? "mp-badge"}>{direction}</span>
}

// Progress bar identical in style to ConfidenceBar in SignalHistoryTable
function ScoreBar({ score }) {
  const pct   = Math.min(100, Math.max(0, (score ?? 0) * 100))
  const color = pct >= 70 ? "#00E676" : pct >= 40 ? "#FFB800" : "#FF3D57"
  return (
    <div className="flex items-center gap-2 min-w-[80px]">
      <div className="relative h-1.5 w-14 overflow-hidden rounded-full bg-mp-border">
        <div
          className="absolute inset-y-0 left-0 rounded-full transition-all"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span className="font-mono text-xs tabular-nums" style={{ color }}>
        {(score ?? 0).toFixed(2)}
      </span>
    </div>
  )
}

function getPEColor(pe, avgPE) {
  if (pe < avgPE * 0.90) return "#00E676"  // below avg → green (cheap)
  if (pe > avgPE * 1.10) return "#FF3D57"  // above avg → red  (expensive)
  return "#C8D8F0"                          // near avg → text colour
}

// Single peer row
function PeerRow({ peer, totalPeers, score, avgPE, onAnalyze }) {
  const isFirst = peer.rank === 1
  const isLast  = peer.rank === totalPeers
  const peColor = getPEColor(peer.metrics.pe_ratio, avgPE)

  const rowBg = isFirst
    ? "bg-mp-saffron/5"
    : isLast
    ? "bg-mp-red/5"
    : ""

  return (
    <tr
      className={`border-b border-mp-border/50 transition-colors
                  hover:bg-mp-surface2 ${rowBg}`}
    >
      {/* Rank */}
      <td className="whitespace-nowrap px-3 py-2.5">
        <div className="flex items-center gap-1.5">
          {isFirst ? (
            <span title="Sector Best" className="text-base leading-none">🏆</span>
          ) : (
            <span className="font-mono text-xs text-mp-dim">
              #{peer.rank}
            </span>
          )}
        </div>
      </td>

      {/* Stock — symbol + company + optional SECTOR BEST badge */}
      <td className="whitespace-nowrap px-3 py-2.5">
        <div className="flex flex-col gap-0.5">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="font-mono text-sm font-bold text-mp-saffron">
              {peer.nse_symbol}
            </span>
            {peer.is_sector_best && (
              <span
                className="font-mono text-[9px] font-bold px-1.5 py-0.5 rounded
                           tracking-wider uppercase"
                style={{
                  color: "#FF9500",
                  backgroundColor: "#FF950014",
                  border: "1px solid #FF950040",
                }}
              >
                SECTOR BEST
              </span>
            )}
          </div>
          <span className="font-sans text-[11px] text-mp-muted max-w-[180px] truncate">
            {peer.company_name}
          </span>
        </div>
      </td>

      {/* Signal */}
      <td className="px-3 py-2.5">
        <SignalBadge direction={peer.latest_signal?.direction} />
      </td>

      {/* P/E Ratio */}
      <td className="whitespace-nowrap px-3 py-2.5">
        <span className="font-mono text-xs font-bold" style={{ color: peColor }}>
          {numFmt(peer.metrics.pe_ratio)}
        </span>
      </td>

      {/* Rev Growth */}
      <td className="whitespace-nowrap px-3 py-2.5">
        <span
          className="font-mono text-xs font-bold"
          style={{ color: peer.metrics.revenue_growth_pct >= 0 ? "#00E676" : "#FF3D57" }}
        >
          {pctFmt(peer.metrics.revenue_growth_pct, true)}
        </span>
      </td>

      {/* PAT Margin */}
      <td className="whitespace-nowrap px-3 py-2.5 font-mono text-xs text-mp-text">
        {pctFmt(peer.metrics.pat_margin_pct)}
      </td>

      {/* ROE */}
      <td className="whitespace-nowrap px-3 py-2.5">
        <span
          className="font-mono text-xs font-bold"
          style={{ color: peer.metrics.roe_pct >= 20 ? "#00E676" : "#C8D8F0" }}
        >
          {pctFmt(peer.metrics.roe_pct)}
        </span>
      </td>

      {/* Score bar */}
      <td className="px-3 py-2.5">
        <ScoreBar score={score} />
      </td>

      {/* Analyse action */}
      <td className="px-3 py-2.5">
        {onAnalyze && (
          <button
            onClick={() => onAnalyze(peer.nse_symbol)}
            className="font-mono text-[11px] text-mp-saffron opacity-0
                       group-hover:opacity-100 hover:text-mp-saffron/80
                       transition-all"
          >
            ▶
          </button>
        )}
      </td>
    </tr>
  )
}

// Section 3 — full peer comparison table
function PeerTable({ data, scores, onAnalyze }) {
  const avgPE = useMemo(() => {
    const pes = data.peers.map((p) => p.metrics.pe_ratio)
    return pes.reduce((a, b) => a + b, 0) / pes.length
  }, [data.peers])

  return (
    <div className="mp-card overflow-hidden p-0">
      {/* Card header */}
      <div className="flex items-center justify-between border-b border-mp-border px-4 py-3">
        <h2 className="font-mono text-sm font-bold text-mp-text">
          🏭 Peer Comparison — {data.sector}
        </h2>
        <span className="font-mono text-xs text-mp-muted">
          {data.peers.length} stocks
        </span>
      </div>

      {/* Scrollable table */}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-xs font-mono">
          <thead>
            <tr className="sticky top-0 border-b border-mp-border bg-mp-surface">
              <th className="px-3 py-2.5 text-left font-mono text-[10px] font-bold
                             tracking-wider text-mp-muted whitespace-nowrap">
                Rank
              </th>
              <th className="px-3 py-2.5 text-left font-mono text-[10px] font-bold
                             tracking-wider text-mp-muted whitespace-nowrap">
                Stock
              </th>
              <th className="px-3 py-2.5 text-left font-mono text-[10px] font-bold
                             tracking-wider text-mp-muted whitespace-nowrap">
                Signal
              </th>
              <th className="px-3 py-2.5 text-left font-mono text-[10px] font-bold
                             tracking-wider text-mp-muted whitespace-nowrap">
                P/E
              </th>
              <th className="px-3 py-2.5 text-left font-mono text-[10px] font-bold
                             tracking-wider text-mp-muted whitespace-nowrap">
                Rev Growth
              </th>
              <th className="px-3 py-2.5 text-left font-mono text-[10px] font-bold
                             tracking-wider text-mp-muted whitespace-nowrap">
                PAT Margin
              </th>
              <th className="px-3 py-2.5 text-left font-mono text-[10px] font-bold
                             tracking-wider text-mp-muted whitespace-nowrap">
                ROE
              </th>
              <th className="px-3 py-2.5 text-left font-mono text-[10px] font-bold
                             tracking-wider text-mp-muted whitespace-nowrap">
                Score
              </th>
              <th className="px-3 py-2.5 w-8" />
            </tr>
          </thead>

          <tbody>
            {data.peers.map((peer, i) => (
              <PeerRow
                key={peer.nse_symbol}
                peer={peer}
                totalPeers={data.peers.length}
                score={scores[i] ?? 0}
                avgPE={avgPE}
                onAnalyze={onAnalyze}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// Section 4 — sector insights summary
function SectorInsights({ data }) {
  const best    = data.peers.find((p) => p.is_sector_best)
  const withSig = data.peers.filter((p) => p.latest_signal)
  const buyCount = withSig.filter((p) => p.latest_signal.direction === "BUY").length
  const sigTotal = withSig.length || data.peers.length

  const fiiColorMap = {
    bullish: "#00E676",
    bearish: "#FF3D57",
    neutral: "#4A5A78",
  }
  const fiiColor = fiiColorMap[data.fii_trend] ?? "#4A5A78"

  return (
    <div className="mp-card">
      <h3 className="font-mono text-xs font-bold text-mp-muted tracking-widest
                     uppercase mb-3">
        💡 Sector Insights
      </h3>

      <div className="flex flex-col gap-2.5">
        {best && (
          <div className="flex items-baseline gap-2">
            <span className="font-mono text-[10px] text-mp-dim whitespace-nowrap">
              Best pick:
            </span>
            <span className="font-mono text-xs text-mp-text">
              <span className="font-bold text-mp-saffron">{best.nse_symbol}</span>
              {" "}leads on composite score
            </span>
          </div>
        )}

        <div className="flex items-baseline gap-2">
          <span className="font-mono text-[10px] text-mp-dim whitespace-nowrap">
            Sector trend:
          </span>
          <span className="font-mono text-xs text-mp-text">
            <span className="font-bold" style={{ color: buyCount > sigTotal / 2 ? "#00E676" : "#C8D8F0" }}>
              {buyCount}
            </span>
            {" "}of{" "}
            <span className="font-bold">{sigTotal}</span>
            {" "}stocks have BUY signals
          </span>
        </div>

        <div className="flex items-baseline gap-2">
          <span className="font-mono text-[10px] text-mp-dim whitespace-nowrap">
            FII:
          </span>
          <span className="font-mono text-xs text-mp-text">
            FII activity:{" "}
            <span className="font-bold capitalize" style={{ color: fiiColor }}>
              {data.fii_trend}
            </span>
          </span>
        </div>
      </div>
    </div>
  )
}

// ─── Loading / error shells ────────────────────────────────────────────────

function LoadingShell() {
  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="flex flex-col items-center gap-3">
        <div
          className="w-6 h-6 border-2 border-mp-saffron/30 border-t-mp-saffron
                     rounded-full animate-spin"
        />
        <span className="font-mono text-xs text-mp-muted animate-pulse">
          Loading sector data…
        </span>
      </div>
    </div>
  )
}

function ErrorShell({ message, onRetry }) {
  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="text-center">
        <div className="text-3xl mb-2">⚠️</div>
        <p className="font-mono text-sm text-mp-red mb-3">{message}</p>
        <button onClick={onRetry} className="mp-btn-ghost text-xs">
          Try again
        </button>
      </div>
    </div>
  )
}

// ─── Main component ────────────────────────────────────────────────────────

export default function SectorPage({ onAnalyze }) {
  const { token } = useAuth()

  const [activeSector, setActiveSector] = useState("IT")
  const [data,         setData]         = useState(null)
  const [loading,      setLoading]      = useState(false)  // GET /sector/rankings
  const [analyzing,    setAnalyzing]    = useState(false)  // POST /sector/analyze
  const [progress,     setProgress]     = useState(0)
  const [error,        setError]        = useState(null)

  // ── Composite scores ──────────────────────────────────────────────────────
  // Live analysis provides composite_score directly (includes PE inversion).
  // Fall back to client-side computation when loading cached GET data.
  const scores = useMemo(() => {
    if (!data) return []
    if (data.peers[0]?._composite_score !== undefined) {
      return data.peers.map((p) => p._composite_score ?? 0)
    }
    return computeScores(data.peers)
  }, [data])

  // ── On mount / tab switch: try to load cached rankings ───────────────────
  // GET /api/sector/rankings/{sector} — currently always 404 (no cache).
  // On 404/error: leave data=null so the empty state shows; do not set error
  // (error state is reserved for POST failures the user should act on).
  useEffect(() => {
    if (!token) return
    setLoading(true)
    setData(null)
    setError(null)

    axios
      .get(`${API}/api/sector/rankings/${activeSector}`, {
        headers: { Authorization: "Bearer " + token },
      })
      .then((res) => setData(normalizeLiveData(res.data)))
      .catch(() => {}) // 404 → empty state; user clicks ▶ Analyse Sector
      .finally(() => setLoading(false))
  }, [activeSector, token]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Analyse Sector button — POST /api/sector/analyze ─────────────────────
  const analyzeSector = async (sector) => {
    setAnalyzing(true)
    setProgress(0)
    setData(null)
    setError(null)

    // Simulate progress while the parallel graph executes (~15-60 s)
    const progressInterval = setInterval(() => {
      setProgress((prev) => Math.min(prev + 8, 90))
    }, 1000)

    try {
      const res = await axios.post(
        `${API}/api/sector/analyze`,
        { sector },
        {
          headers: {
            "Content-Type": "application/json",
            Authorization: "Bearer " + token,
          },
        },
      )
      clearInterval(progressInterval)
      setProgress(100)
      setData(normalizeLiveData(res.data))
    } catch (e) {
      clearInterval(progressInterval)
      setError(e.response?.data?.detail || "Analysis failed")
    } finally {
      setAnalyzing(false)
    }
  }

  return (
    <div className="flex flex-col gap-4 p-4 h-full overflow-auto">

      {/* ── Section 1: Sector tabs + Analyse button ── */}
      <SectorTabs active={activeSector} onChange={setActiveSector}>
        <button
          onClick={() => analyzeSector(activeSector)}
          disabled={loading || analyzing}
          className="mp-btn-primary text-xs px-3 py-1.5 ml-auto"
        >
          {analyzing ? "Analyzing..." : "▶ Analyse Sector"}
        </button>
      </SectorTabs>

      {/* ── Progress bar (while parallel analysis is running) ── */}
      {analyzing && (
        <div className="mp-card">
          <div className="flex items-center gap-3 mb-3">
            <div className="flex gap-1">
              {[...Array(5)].map((_, i) => (
                <div
                  key={i}
                  className="w-2 h-2 rounded-full bg-mp-saffron animate-pulse"
                  style={{ animationDelay: `${i * 0.15}s` }}
                />
              ))}
            </div>
            <span className="text-xs font-mono text-mp-saffron">
              Analyzing {activeSector} sector in parallel...
            </span>
          </div>

          {/* Smooth progress bar — fills via CSS transition-all */}
          <div className="h-1.5 bg-mp-surface2 rounded-full overflow-hidden">
            <div
              className="h-full bg-mp-saffron rounded-full transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>

          <div className="flex justify-between mt-2 text-xs font-mono text-mp-dim">
            <span>Running 5 parallel analyses...</span>
            <span>{progress}%</span>
          </div>

          {/* Per-stock pulse tiles */}
          <div className="grid grid-cols-5 gap-2 mt-3">
            {SECTOR_SYMBOLS[activeSector]?.map((sym, i) => (
              <div
                key={sym}
                className="text-center p-2 rounded border border-mp-border
                           bg-mp-surface2 animate-pulse"
                style={{ animationDelay: `${i * 0.2}s` }}
              >
                <div className="text-xs font-mono text-mp-saffron font-bold">
                  {sym}
                </div>
                <div className="text-xs text-mp-dim mt-0.5">
                  analyzing...
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Simple spinner — while GET /sector/rankings is in flight ── */}
      {loading && !analyzing && <LoadingShell />}

      {/* ── Error ── */}
      {!loading && !analyzing && error && (
        <ErrorShell
          message={error}
          onRetry={() => analyzeSector(activeSector)}
        />
      )}

      {/* ── Results ── */}
      {!loading && !analyzing && !error && data && (
        <>
          {/* Section 2: Summary bar */}
          <SectorSummaryBar data={data} />

          {/* Section 3: Peer comparison table */}
          <PeerTable data={data} scores={scores} onAnalyze={onAnalyze} />

          {/* Section 4: Sector insights */}
          <SectorInsights data={data} />

          {/* SEBI disclaimer — mandatory: page renders BUY/SELL/HOLD signals */}
          <p className="font-mono text-[10px] leading-relaxed text-mp-dim
                        border-t border-mp-border pt-3 mt-auto">
            ⚠️ MarketPulse India is not a SEBI-registered investment advisor.
            Output is for educational/informational purposes only and is not
            investment advice. Markets carry risk; consult a registered advisor
            before making decisions.
          </p>
        </>
      )}

    </div>
  )
}
