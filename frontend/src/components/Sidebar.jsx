import { useState } from "react"
import { useAuth } from "../context/AuthContext"
import { useWatchlist } from "../hooks/useMarketData"

// ─── Signal badge ──────────────────────────────────────────────────────────

function SignalBadge({ direction }) {
  if (!direction) return null
  const classes = {
    BUY:  "mp-badge-buy",
    SELL: "mp-badge-sell",
    HOLD: "mp-badge-hold",
  }
  return (
    <span className={`mp-badge ${classes[direction] ?? ""}`}>
      {direction}
    </span>
  )
}

// ─── Single watchlist row ──────────────────────────────────────────────────

function WatchlistItem({ item, isActive, onAnalyze, onRemove }) {
  const [loading, setLoading] = useState(false)

  const handleAnalyze = async () => {
    setLoading(true)
    await onAnalyze(item.nse_symbol)
    setLoading(false)
  }

  const sig = item.latest_signal

  return (
    <div
      className={`group flex items-center justify-between
                 px-3 py-2.5 border-b border-mp-border/50
                 border-l-2 transition-colors cursor-pointer
                 ${
                   isActive
                     ? "border-l-mp-saffron bg-mp-saffron/5"
                     : "border-l-transparent hover:bg-mp-surface2"
                 }`}
      onClick={handleAnalyze}
    >
      <div className="flex-1 min-w-0">
        {/* Line 1: symbol + signal badge */}
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm font-bold text-mp-text truncate">
            {item.nse_symbol}
          </span>
          <SignalBadge direction={sig?.direction} />
        </div>

        {/* Line 2: company name or sector */}
        {(item.company_name || item.sector) && (
          <div className="mt-0.5 flex items-center gap-1.5">
            {item.company_name && item.company_name !== item.nse_symbol ? (
              <span className="text-xs text-mp-muted font-sans truncate">
                {item.company_name}
              </span>
            ) : item.sector ? (
              <span className="text-xs text-mp-dim font-mono">{item.sector}</span>
            ) : null}
            {item.company_name && item.company_name !== item.nse_symbol && item.sector && (
              <span className="text-xs text-mp-dim font-mono">· {item.sector}</span>
            )}
          </div>
        )}

        {/* Line 3: LTP + confidence */}
        <div className="flex items-center gap-2 mt-0.5">
          {sig?.current_price_inr != null && (
            <span className="text-xs font-mono text-mp-muted">
              ₹{sig.current_price_inr.toLocaleString("en-IN")}
            </span>
          )}
          {sig?.confidence != null && (
            <span className="text-xs text-mp-dim font-mono">
              {(sig.confidence * 100).toFixed(0)}%
            </span>
          )}
          {sig?.upside_pct != null && (
            <span
              className={`text-xs font-mono ${
                sig.upside_pct >= 0 ? "text-mp-green" : "text-mp-red"
              }`}
            >
              {sig.upside_pct >= 0 ? "+" : ""}
              {sig.upside_pct.toFixed(1)}%
            </span>
          )}
        </div>
      </div>

      {/* Actions — reveal on hover */}
      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity ml-1 flex-shrink-0">
        {loading ? (
          <span className="text-xs text-mp-saffron animate-pulse">…</span>
        ) : (
          <span className="text-xs text-mp-saffron">▶</span>
        )}
        <button
          onClick={(e) => {
            e.stopPropagation()
            onRemove(item.nse_symbol)
          }}
          className="text-mp-muted hover:text-mp-red text-xs px-1 transition-colors"
        >
          ✕
        </button>
      </div>
    </div>
  )
}

// ─── Add-stock form ────────────────────────────────────────────────────────

function AddStockForm({ onAdd }) {
  const [symbol, setSymbol] = useState("")
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState("")

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!symbol.trim()) return
    setLoading(true)
    setError("")
    const ok = await onAdd(symbol.trim().toUpperCase())
    if (ok) {
      setSymbol("")
    } else {
      setError("Symbol not found on NSE")
    }
    setLoading(false)
  }

  return (
    <form onSubmit={handleSubmit} className="p-3 border-t border-mp-border">
      <div className="flex gap-2">
        <input
          type="text"
          value={symbol}
          onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          placeholder="Add symbol…"
          className="mp-input text-xs py-1.5"
          maxLength={20}
        />
        <button
          type="submit"
          disabled={loading}
          className="mp-btn-primary text-xs px-3 whitespace-nowrap"
        >
          {loading ? "…" : "+"}
        </button>
      </div>
      {error && (
        <p className="text-mp-red text-xs mt-1 font-mono">{error}</p>
      )}
    </form>
  )
}

// ─── Sidebar ───────────────────────────────────────────────────────────────

export default function Sidebar({ onAnalyze, activeSymbol }) {
  const { token } = useAuth()
  const { items, loading, addStock, removeStock } = useWatchlist(token)

  return (
    <aside
      className="w-64 bg-mp-surface border-r border-mp-border
                 flex flex-col h-full overflow-hidden"
    >
      {/* Header */}
      <div className="px-4 py-3 border-b border-mp-border">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold text-mp-muted tracking-widest uppercase">
            Watchlist
          </span>
          <span className="text-xs text-mp-muted font-mono">
            {items.length} stocks
          </span>
        </div>
      </div>

      {/* Item list */}
      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="p-4 text-mp-muted text-xs text-center animate-pulse">
            Loading…
          </div>
        ) : items.length === 0 ? (
          <div className="p-4 text-mp-muted text-xs text-center leading-relaxed">
            Add stocks to your watchlist to start tracking signals
          </div>
        ) : (
          items.map((item) => (
            <WatchlistItem
              key={item.nse_symbol}
              item={item}
              isActive={item.nse_symbol === activeSymbol}
              onAnalyze={onAnalyze}
              onRemove={removeStock}
            />
          ))
        )}
      </div>

      {/* Add stock */}
      <AddStockForm onAdd={addStock} />
    </aside>
  )
}
