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

function WatchlistItem({ item, onAnalyze, onRemove }) {
  const [loading, setLoading] = useState(false)

  const handleAnalyze = async () => {
    setLoading(true)
    await onAnalyze(item.nse_symbol)
    setLoading(false)
  }

  return (
    <div
      className="group flex items-center justify-between
                 px-3 py-2.5 hover:bg-mp-surface2
                 border-b border-mp-border/50
                 transition-colors cursor-pointer"
      onClick={handleAnalyze}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-mono text-sm font-bold text-mp-text truncate">
            {item.nse_symbol}
          </span>
          <SignalBadge direction={item.latest_signal?.direction} />
        </div>
        <div className="flex items-center gap-2 mt-0.5">
          {item.latest_signal?.current_price_inr && (
            <span className="text-xs font-mono text-mp-muted">
              ₹{item.latest_signal.current_price_inr.toLocaleString("en-IN")}
            </span>
          )}
          {item.latest_signal?.confidence && (
            <span className="text-xs text-mp-muted">
              {(item.latest_signal.confidence * 100).toFixed(0)}%
            </span>
          )}
        </div>
      </div>

      {/* Actions — reveal on hover */}
      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
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

export default function Sidebar({ onAnalyze }) {
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
