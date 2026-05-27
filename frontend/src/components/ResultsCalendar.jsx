import { useState, useEffect } from "react"
import axios from "axios"
import { useAuth } from "../context/AuthContext"

const API = ""

// ─── Date helpers ──────────────────────────────────────────────────────────
// Parse "YYYY-MM-DD" as a local (not UTC) date to avoid midnight-UTC → previous
// day in IST (UTC+5:30) timezone drift.

function parseDate(str) {
  const [y, m, d] = str.split("-").map(Number)
  return new Date(y, m - 1, d)
}

const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
const WEEKDAYS = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]

// "Friday, 18 Jul 2026"
function formatDateLong(str) {
  const d = parseDate(str)
  return `${WEEKDAYS[d.getDay()]}, ${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`
}

// "Jul 15 – Aug 15, 2026"
function formatSeasonRange(start, end) {
  const s = parseDate(start)
  const e = parseDate(end)
  return `${MONTHS[s.getMonth()]} ${s.getDate()} – ${MONTHS[e.getMonth()]} ${e.getDate()}, ${e.getFullYear()}`
}

// "in 49 days" | "Tomorrow" | "Today" | null (past)
function daysUntilLabel(str) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const diff = Math.round((parseDate(str) - today) / 86_400_000)
  if (diff < 0) return null
  if (diff === 0) return "Today"
  if (diff === 1) return "Tomorrow"
  return `in ${diff} days`
}

// Relative label shown next to the date header, only within 7 days
function relativeDateLabel(str) {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const diff = Math.round((parseDate(str) - today) / 86_400_000)
  if (diff === 0) return "Today"
  if (diff === 1) return "Tomorrow"
  if (diff > 1 && diff <= 7) return `In ${diff} days`
  return null
}

// ─── Sector colour helper ──────────────────────────────────────────────────

function getSectorColor(sector) {
  const map = {
    "IT": "#38BDF8",
    "Banking": "#FF9500",
    "FMCG": "#00E676",
    "Pharma": "#A78BFA",
    "NBFC": "#FFB800",
    "Consumer": "#F472B6",
    "Financial Services": "#FF9500",
  }
  return map[sector] || "#4A5A78"
}

// ─── Section 1: Results-season active banner ───────────────────────────────

function SeasonActiveBanner() {
  return (
    <div
      className="flex items-center gap-3 rounded-lg px-4 py-3
                 bg-mp-saffron/10 border border-mp-saffron/40"
    >
      {/* Pulsing dot */}
      <span className="relative flex h-2.5 w-2.5 flex-shrink-0">
        <span
          className="animate-ping absolute inline-flex h-full w-full
                     rounded-full bg-mp-saffron opacity-75"
        />
        <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-mp-saffron" />
      </span>
      <span className="font-mono text-xs font-bold text-mp-saffron tracking-wider">
        🔔 RESULTS SEASON ACTIVE — Enhanced monitoring ON
      </span>
    </div>
  )
}

// ─── Section 2: Individual season card ────────────────────────────────────

function SeasonCard({ season }) {
  const label = daysUntilLabel(season.start)

  return (
    <div
      className={`flex flex-col gap-1.5 rounded-lg border px-4 py-3
                 min-w-[200px] max-w-[260px] flex-shrink-0
                 ${season.is_active
                   ? "border-mp-saffron/40 bg-mp-saffron/5"
                   : "border-mp-border bg-mp-surface2"}`}
    >
      {/* Name row + status */}
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono text-xs font-bold text-mp-text leading-snug">
          {season.name}
        </span>
        {season.is_active ? (
          <span className="mp-badge-buy flex-shrink-0">ACTIVE</span>
        ) : label ? (
          <span className="font-mono text-[10px] text-mp-muted flex-shrink-0 whitespace-nowrap">
            {label}
          </span>
        ) : null}
      </div>

      {/* Date range */}
      <span className="font-mono text-[11px] text-mp-muted">
        {formatSeasonRange(season.start, season.end)}
      </span>
    </div>
  )
}

// ─── Section 3: Pre-Analyse button (self-contained loading state) ──────────

function PreAnalyseButton({ symbol, token }) {
  const [state, setState] = useState(null) // null | "loading" | "done"

  async function handleClick() {
    if (state === "loading" || state === "done") return
    setState("loading")
    try {
      await axios.post(
        `${API}/api/analyze/${symbol}`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      )
      setState("done")
    } catch (e) {
      console.error("Pre-analyse error:", e)
      setState(null)
    }
  }

  if (state === "done") {
    return (
      <span className="font-mono text-xs font-bold text-mp-green flex items-center gap-1">
        Queued ✓
      </span>
    )
  }

  return (
    <button
      onClick={handleClick}
      disabled={state === "loading"}
      className={`mp-btn-primary text-[11px] px-2.5 py-1 flex items-center gap-1.5
                 ${state === "loading" ? "opacity-60 cursor-not-allowed" : ""}`}
    >
      {state === "loading" ? (
        <>
          <span
            className="w-3 h-3 border-2 border-black/30 border-t-black
                       rounded-full animate-spin inline-block flex-shrink-0"
          />
          Queuing…
        </>
      ) : (
        <>▶ Pre-Analyse</>
      )}
    </button>
  )
}

// ─── Section 3: Individual stock result card ───────────────────────────────

function StockResultCard({ stock, token }) {
  const sectorColor = getSectorColor(stock.sector)
  const isPost = stock.expected_time === "post-market"

  return (
    <div
      className="flex items-center justify-between gap-3
                 px-4 py-3 bg-mp-surface2 rounded-lg
                 border border-mp-border
                 hover:border-mp-saffron/30 transition-colors"
    >
      {/* Left: symbol + company + badges */}
      <div className="flex flex-col gap-1 min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap">
          {/* NSE symbol */}
          <span className="font-mono text-sm font-bold text-mp-saffron">
            {stock.nse_symbol}
          </span>

          {/* Sector badge — colour-coded inline */}
          <span
            className="font-mono text-[10px] font-bold px-1.5 py-0.5 rounded
                       tracking-wider uppercase flex-shrink-0"
            style={{
              color: sectorColor,
              backgroundColor: `${sectorColor}1A`,       // ~10% opacity
              border: `1px solid ${sectorColor}40`,      // ~25% opacity
            }}
          >
            {stock.sector}
          </span>

          {/* Expected-time badge */}
          <span
            className={`font-mono text-[10px] px-1.5 py-0.5 rounded
                       tracking-wider uppercase flex-shrink-0
                       ${isPost
                         ? "text-mp-muted bg-mp-border/30 border border-mp-border"
                         : "text-mp-blue bg-mp-blue/10 border border-mp-blue/30"}`}
          >
            {isPost ? "Post-Market" : "Pre-Market"}
          </span>
        </div>

        {/* Company name */}
        <span className="font-sans text-xs text-mp-muted truncate">
          {stock.company_name}
        </span>
      </div>

      {/* Right: Pre-Analyse button */}
      <div className="flex-shrink-0">
        <PreAnalyseButton symbol={stock.nse_symbol} token={token} />
      </div>
    </div>
  )
}

// ─── Section 3: Date group (header + stock cards) ─────────────────────────

function DateGroup({ day, token }) {
  const rel = relativeDateLabel(day.date)
  const count = day.stocks.length

  return (
    <div className="flex flex-col gap-2">
      {/* Date header row */}
      <div className="flex items-center gap-2.5 flex-wrap">
        <span className="font-mono text-xs font-bold text-mp-text">
          {formatDateLong(day.date)}
        </span>

        {/* Relative label (within 7 days only) */}
        {rel && (
          <span
            className="font-mono text-[10px] font-bold px-1.5 py-0.5 rounded
                       bg-mp-saffron/10 text-mp-saffron border border-mp-saffron/30
                       tracking-wider uppercase"
          >
            {rel}
          </span>
        )}

        <span className="font-mono text-[10px] text-mp-dim">
          {count} result{count !== 1 ? "s" : ""}
        </span>
      </div>

      {/* Stock cards indented under the date */}
      <div className="flex flex-col gap-1.5 pl-3 border-l border-mp-border">
        {day.stocks.map((stock) => (
          <StockResultCard key={stock.nse_symbol} stock={stock} token={token} />
        ))}
      </div>
    </div>
  )
}

// ─── Section 4: Empty state ────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="mp-card text-center py-10">
      <div className="text-3xl mb-3">📅</div>
      <p className="font-mono text-sm text-mp-muted leading-relaxed">
        No upcoming results in your watchlist.
      </p>
      <p className="font-mono text-xs text-mp-dim mt-1">
        Add stocks to track their result dates.
      </p>
    </div>
  )
}

// ─── Main component ────────────────────────────────────────────────────────

export default function ResultsCalendar() {
  const { token } = useAuth()

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!token) return
    setLoading(true)
    setError(null)

    axios
      .get(`${API}/api/market/results-calendar`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      .then((res) => setData(res.data))
      .catch(() => setError("Failed to load results calendar."))
      .finally(() => setLoading(false))
  }, [token])

  // ── Loading ──────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="font-mono text-sm text-mp-muted animate-pulse">
          Loading results calendar…
        </span>
      </div>
    )
  }

  // ── Error ────────────────────────────────────────────────────────────────
  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <div className="text-3xl mb-2">⚠️</div>
          <p className="font-mono text-sm text-mp-red">{error}</p>
        </div>
      </div>
    )
  }

  const { seasons = [], upcoming = [], is_results_season: isActive = false } = data ?? {}

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-6 p-4 overflow-auto">

      {/* ── Section 1: Active season banner (conditional) ── */}
      {isActive && <SeasonActiveBanner />}

      {/* ── Section 2: Season cards ── */}
      <div>
        <h2
          className="font-mono text-xs font-bold text-mp-muted
                     tracking-widest uppercase mb-3"
        >
          Results Seasons
        </h2>
        <div className="flex gap-3 flex-wrap">
          {seasons.map((season) => (
            <SeasonCard key={season.name} season={season} />
          ))}
        </div>
      </div>

      {/* ── Section 3 / 4: Upcoming results or empty state ── */}
      <div>
        <h2
          className="font-mono text-xs font-bold text-mp-muted
                     tracking-widest uppercase mb-3"
        >
          Upcoming Results · Next 90 Days
        </h2>

        {upcoming.length === 0 ? (
          <EmptyState />
        ) : (
          <div className="flex flex-col gap-6">
            {upcoming.map((day) => (
              <DateGroup key={day.date} day={day} token={token} />
            ))}
          </div>
        )}
      </div>

    </div>
  )
}
