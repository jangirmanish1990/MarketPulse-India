import { useISTClock, useMarketData } from "../hooks/useMarketData"
import { useAuth } from "../context/AuthContext"

// ─── Index ticker pill ─────────────────────────────────────────────────────

function IndexTicker({ label, value, change }) {
  const isUp = change >= 0
  return (
    <div className="flex items-center gap-2 px-3 py-1
                    border-r border-mp-border last:border-0">
      <span className="text-mp-muted text-xs">{label}</span>
      <span className="font-mono text-sm font-bold text-mp-text">
        {value?.toLocaleString("en-IN", { maximumFractionDigits: 2 }) ?? "—"}
      </span>
      <span className={`text-xs font-mono ${isUp ? "text-mp-green" : "text-mp-red"}`}>
        {isUp ? "+" : ""}
        {change?.toFixed(2) ?? "0.00"}%
      </span>
    </div>
  )
}

// ─── Market status badge ───────────────────────────────────────────────────

function MarketStatusBadge({ status }) {
  const configs = {
    OPEN:        { label: "OPEN",        cls: "mp-badge-open",   dot: "bg-mp-green",  pulse: true  },
    CLOSED:      { label: "CLOSED",      cls: "mp-badge-closed", dot: "bg-mp-muted",  pulse: false },
    PRE_MARKET:  { label: "PRE-MARKET",  cls: "mp-badge-hold",   dot: "bg-mp-yellow", pulse: false },
    POST_MARKET: { label: "POST-MARKET", cls: "mp-badge-hold",   dot: "bg-mp-yellow", pulse: false },
    WEEKEND:     { label: "WEEKEND",     cls: "mp-badge-closed", dot: "bg-mp-muted",  pulse: false },
  }
  const cfg = configs[status] ?? configs.CLOSED

  return (
    <div className={`mp-badge ${cfg.cls} flex items-center gap-1.5`}>
      <span
        className={`w-1.5 h-1.5 rounded-full ${cfg.dot} ${cfg.pulse ? "animate-pulse" : ""}`}
      />
      {cfg.label}
    </div>
  )
}

// ─── Header ────────────────────────────────────────────────────────────────

export default function Header() {
  const { token, user, logout } = useAuth()
  const { time, date } = useISTClock()
  const { data: market } = useMarketData(token)

  return (
    <header
      className="h-14 bg-mp-surface border-b border-mp-border
                 flex items-center justify-between px-4
                 sticky top-0 z-50"
    >
      {/* ── Logo ── */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="text-mp-saffron text-lg">📈</span>
          <span className="font-sans font-bold text-white text-lg tracking-tight">
            Market<span className="text-mp-saffron">Pulse</span>
          </span>
          <span className="text-mp-muted text-sm hidden sm:block">India</span>
        </div>
        <span className="hidden md:block">
          <MarketStatusBadge status={market?.market_status || "CLOSED"} />
        </span>
      </div>

      {/* ── Index tickers (desktop) ── */}
      <div
        className="hidden lg:flex items-center
                   bg-mp-surface2 rounded border border-mp-border
                   overflow-hidden"
      >
        <IndexTicker
          label="NIFTY"
          value={market?.nifty50?.value}
          change={market?.nifty50?.change_pct}
        />
        <IndexTicker
          label="SENSEX"
          value={market?.sensex?.value}
          change={market?.sensex?.change_pct}
        />
        <IndexTicker
          label="BANK"
          value={market?.nifty_bank?.value}
          change={market?.nifty_bank?.change_pct}
        />
        <IndexTicker
          label="IT"
          value={market?.nifty_it?.value}
          change={market?.nifty_it?.change_pct}
        />
        <div className="px-3 py-1 text-xs font-mono text-mp-muted border-l border-mp-border">
          ₹/{market?.usd_inr?.toFixed(2) ?? "—"}
        </div>
      </div>

      {/* ── IST clock + user ── */}
      <div className="flex items-center gap-4">
        <div className="hidden sm:flex flex-col items-end">
          <span className="font-mono text-sm text-mp-saffron font-bold tracking-wider">
            {time}
          </span>
          <span className="font-mono text-xs text-mp-muted">{date} IST</span>
        </div>
        {user && (
          <button onClick={logout} className="mp-btn-ghost text-xs px-3 py-1.5">
            {user.name || user.email}
          </button>
        )}
      </div>
    </header>
  )
}
