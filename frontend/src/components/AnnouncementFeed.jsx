import { useState, useEffect, useCallback } from "react"
import axios from "axios"
import { useAuth } from "../context/AuthContext"

const API = ""

// ─── Relative-time helper ──────────────────────────────────────────────────

function timeAgo(isoString) {
  const diff  = Date.now() - new Date(isoString).getTime()
  const mins  = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days  = Math.floor(diff / 86400000)
  if (mins  < 1)  return "just now"
  if (mins  < 60) return `${mins}m ago`
  if (hours < 24) return `${hours}h ago`
  return `${days}d ago`
}

// ─── Announcement-type config ──────────────────────────────────────────────
// Maps announcement_type string → display label + Tailwind classes.
// This table is the "ready for real NSE webhook data" contract: when the
// backend starts sending actual announcement types, the UI will just work.

const TYPE_MAP = {
  quarterly_results: {
    label:     "📊 Q Results",
    textCls:   "text-mp-green",
    bgCls:     "bg-mp-green/10",
    borderCls: "border-mp-green/30",
  },
  board_meeting: {
    label:     "📋 Board",
    textCls:   "text-mp-blue",
    bgCls:     "bg-mp-blue/10",
    borderCls: "border-mp-blue/30",
  },
  insider_trade: {
    label:     "👤 Insider",
    textCls:   "text-mp-yellow",
    bgCls:     "bg-mp-yellow/10",
    borderCls: "border-mp-yellow/30",
  },
  shareholding: {
    label:     "📈 SHP",
    textCls:   "text-mp-purple",
    bgCls:     "bg-mp-purple/10",
    borderCls: "border-mp-purple/30",
  },
  manual: {
    label:     "🔍 Manual",
    textCls:   "text-mp-saffron",
    bgCls:     "bg-mp-saffron/10",
    borderCls: "border-mp-saffron/30",
  },
  other: {
    label:     "📌 Other",
    textCls:   "text-mp-muted",
    bgCls:     "bg-mp-border/30",
    borderCls: "border-mp-border",
  },
}

function getTypeConfig(type) {
  return TYPE_MAP[type] ?? TYPE_MAP.other
}

// ─── Static company-name lookup ────────────────────────────────────────────
// Used to hydrate feed items that come from /signals/recent (which doesn't
// carry company_name).  Keeps the feed readable without an extra API call.

const COMPANY_NAMES = {
  TCS:        "Tata Consultancy Services",
  INFY:       "Infosys Ltd",
  WIPRO:      "Wipro Ltd",
  HCLTECH:    "HCL Technologies",
  HDFCBANK:   "HDFC Bank Ltd",
  ICICIBANK:  "ICICI Bank Ltd",
  AXISBANK:   "Axis Bank Ltd",
  KOTAKBANK:  "Kotak Mahindra Bank",
  SBIN:       "State Bank of India",
  RELIANCE:   "Reliance Industries",
  BAJFINANCE: "Bajaj Finance Ltd",
  TITAN:      "Titan Company Ltd",
  NESTLEIND:  "Nestle India Ltd",
  SUNPHARMA:  "Sun Pharma Industries",
}

// ─── Sub-components ────────────────────────────────────────────────────────

function TypeBadge({ type }) {
  const { label, textCls, bgCls, borderCls } = getTypeConfig(type)
  return (
    <span
      className={`font-mono text-[10px] font-bold px-1.5 py-0.5 rounded
                  tracking-wider uppercase flex-shrink-0 border
                  ${textCls} ${bgCls} ${borderCls}`}
    >
      {label}
    </span>
  )
}

function ExchangeBadge({ exchange = "NSE" }) {
  const isNSE = exchange === "NSE"
  return (
    <span
      className={`font-mono text-[10px] font-bold px-1.5 py-0.5 rounded-full
                  tracking-wider uppercase flex-shrink-0 border
                  ${isNSE
                    ? "text-mp-blue   bg-mp-blue/10   border-mp-blue/30"
                    : "text-mp-saffron bg-mp-saffron/10 border-mp-saffron/30"}`}
    >
      {exchange}
    </span>
  )
}

function SignalBadge({ direction }) {
  if (!direction) return null
  const cls = {
    BUY:  "mp-badge-buy",
    SELL: "mp-badge-sell",
    HOLD: "mp-badge-hold",
  }
  return (
    <span className={`mp-badge ${cls[direction] ?? ""}`}>
      {direction}
    </span>
  )
}

// Analyse → button — hidden until the row is hovered; shows a spinner while
// the POST is in-flight, then locks to "Queued ✓" on success.
function AnalyseButton({ symbol, token }) {
  const [state, setState] = useState(null) // null | "loading" | "done"

  async function handleClick(e) {
    e.stopPropagation()
    if (state === "loading" || state === "done") return
    setState("loading")
    try {
      await axios.post(
        `${API}/api/analyze/${symbol}`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      )
      setState("done")
    } catch (err) {
      console.error("Analyse error:", err)
      setState(null) // reset so the user can retry
    }
  }

  if (state === "done") {
    return (
      <span className="font-mono text-xs font-bold text-mp-green flex-shrink-0">
        Queued ✓
      </span>
    )
  }

  return (
    <button
      onClick={handleClick}
      disabled={state === "loading"}
      className={`font-mono text-xs text-mp-saffron
                  hover:text-mp-saffron/80 transition-colors
                  flex items-center gap-1 flex-shrink-0
                  ${state !== "loading"
                    ? "opacity-0 group-hover:opacity-100 transition-opacity"
                    : ""}`}
    >
      {state === "loading" ? (
        <span
          className="w-3 h-3 border-2 border-mp-saffron/30 border-t-mp-saffron
                     rounded-full animate-spin inline-block"
        />
      ) : (
        "Analyse →"
      )}
    </button>
  )
}

// Single feed item row
function FeedItem({ item, token }) {
  return (
    <div
      className="group flex items-start gap-3 px-4 py-3
                 border-b border-mp-border/50
                 hover:bg-mp-surface2 transition-colors
                 animate-fade-in"
    >
      {/* Left: type badge + timestamp stacked */}
      <div className="flex flex-col items-start gap-1 pt-0.5 flex-shrink-0 w-[88px]">
        <TypeBadge type={item.announcement_type} />
        <span className="font-mono text-[10px] text-mp-dim whitespace-nowrap">
          {timeAgo(item.created_ist)}
        </span>
      </div>

      {/* Centre: symbol + exchange + signal + company name */}
      <div className="flex-1 min-w-0 flex flex-col gap-1">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="font-mono text-sm font-bold text-mp-saffron">
            {item.nse_symbol}
          </span>
          <ExchangeBadge exchange={item.exchange} />
          {item.direction && <SignalBadge direction={item.direction} />}
        </div>

        {item.company_name && (
          <span className="font-sans text-xs text-mp-muted truncate">
            {item.company_name}
          </span>
        )}
      </div>

      {/* Right: hover-revealed Analyse button */}
      <div className="flex items-center self-center flex-shrink-0">
        <AnalyseButton symbol={item.nse_symbol} token={token} />
      </div>
    </div>
  )
}

// Feed header — title, live dot, item count, refresh button
function FeedHeader({ onRefresh, refreshing, count }) {
  return (
    <div
      className="flex items-center justify-between
                 px-4 py-3 border-b border-mp-border flex-shrink-0"
    >
      {/* Left: title + live subtitle */}
      <div className="flex flex-col gap-0.5">
        <span className="font-mono text-sm font-bold text-mp-text">
          📡 Announcement Feed
        </span>
        <div className="flex items-center gap-1.5">
          {/* Pulsing green dot */}
          <span className="relative flex h-1.5 w-1.5 flex-shrink-0">
            <span
              className="animate-ping absolute inline-flex h-full w-full
                         rounded-full bg-mp-green opacity-75"
            />
            <span
              className="relative inline-flex h-1.5 w-1.5 rounded-full bg-mp-green"
            />
          </span>
          <span className="font-mono text-[10px] text-mp-muted tracking-wider">
            Live · NSE + BSE
          </span>
          {count > 0 && (
            <span className="font-mono text-[10px] text-mp-dim">
              · {count} event{count !== 1 ? "s" : ""}
            </span>
          )}
        </div>
      </div>

      {/* Right: refresh button */}
      <button
        onClick={onRefresh}
        disabled={refreshing}
        title="Refresh feed"
        className={`p-1.5 rounded text-mp-muted hover:text-mp-text
                    hover:bg-mp-surface2 transition-colors select-none
                    ${refreshing ? "opacity-40 cursor-not-allowed" : ""}`}
      >
        {/* ↺ spins while refreshing */}
        <span
          className={`inline-block text-lg leading-none
                      ${refreshing ? "animate-spin" : ""}`}
        >
          ↺
        </span>
      </button>
    </div>
  )
}

// Empty state — shown before any analysis is triggered
function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-14 px-4 text-center">
      <div className="text-3xl mb-3 opacity-50">📡</div>
      <p className="font-mono text-sm text-mp-muted leading-relaxed">
        No announcements yet.
      </p>
      <p className="font-mono text-xs text-mp-dim mt-1">
        Trigger an analysis to see activity.
      </p>
    </div>
  )
}

// ─── Main component ────────────────────────────────────────────────────────

export default function AnnouncementFeed() {
  const { token } = useAuth()

  const [items,      setItems]      = useState([])
  const [loading,    setLoading]    = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error,      setError]      = useState(null)

  // Fetch /api/signals/recent and adapt the shape to the announcement feed.
  // silent=true → only toggles the refresh-button spinner (no full loading state).
  const fetchFeed = useCallback(
    async ({ silent = false } = {}) => {
      if (!token) return

      if (silent) {
        setRefreshing(true)
      } else {
        setLoading(true)
        setError(null)
      }

      try {
        const res = await axios.get(`${API}/api/signals/recent`, {
          headers: { Authorization: `Bearer ${token}` },
        })

        const signals = res.data.signals ?? []

        // Adapt each Signal → announcement-feed item.
        // When real NSE webhook data arrives, this mapping layer gets replaced
        // with the actual announcement fields; the UI components stay the same.
        setItems(
          signals.map((sig) => ({
            id:                sig.signal_id,
            nse_symbol:        sig.nse_symbol,
            company_name:      COMPANY_NAMES[sig.nse_symbol] ?? null,
            announcement_type: "manual",   // all analysis-triggered events
            exchange:          "NSE",
            direction:         sig.direction,
            confidence:        sig.confidence,
            created_ist:       sig.created_ist,
          }))
        )
      } catch (e) {
        console.error("Feed fetch error:", e)
        // Don't show the error banner for silent polls — keep existing items.
        if (!silent) setError("Failed to load feed.")
      } finally {
        if (silent) {
          setRefreshing(false)
        } else {
          setLoading(false)
        }
      }
    },
    [token]
  )

  // Mount: initial fetch, then poll every 30 s. Cleanup on unmount / token change.
  useEffect(() => {
    if (!token) return
    fetchFeed()
    const id = setInterval(() => fetchFeed({ silent: true }), 30_000)
    return () => clearInterval(id)
  }, [fetchFeed])

  // ── Loading (first paint only) ─────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex flex-col h-full overflow-hidden">
        <FeedHeader onRefresh={() => fetchFeed({ silent: true })} refreshing={false} count={0} />
        <div className="flex-1 flex items-center justify-center">
          <span className="font-mono text-sm text-mp-muted animate-pulse">
            Loading feed…
          </span>
        </div>
      </div>
    )
  }

  // ── Error (initial load failed) ────────────────────────────────────────
  if (error) {
    return (
      <div className="flex flex-col h-full overflow-hidden">
        <FeedHeader
          onRefresh={() => fetchFeed()}
          refreshing={refreshing}
          count={0}
        />
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <div className="text-3xl mb-2">⚠️</div>
            <p className="font-mono text-sm text-mp-red mb-3">{error}</p>
            <button
              onClick={() => fetchFeed()}
              className="mp-btn-ghost text-xs"
            >
              Try again
            </button>
          </div>
        </div>
      </div>
    )
  }

  // ── Feed ───────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* Header */}
      <FeedHeader
        onRefresh={() => fetchFeed({ silent: true })}
        refreshing={refreshing}
        count={items.length}
      />

      {/* Scrollable feed list */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {items.length === 0 ? (
          <EmptyState />
        ) : (
          items.map((item) => (
            <FeedItem key={item.id} item={item} token={token} />
          ))
        )}
      </div>

    </div>
  )
}
