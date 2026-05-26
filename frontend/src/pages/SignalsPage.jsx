import { useAuth }            from "../context/AuthContext"
import { useWS }             from "../context/WebSocketContext"
import { useSignals }        from "../hooks/useSignals"
import PriceChart            from "../components/PriceChart"
import SignalHistoryTable    from "../components/SignalHistoryTable"

// ─── Helpers ───────────────────────────────────────────────────────────────

function inrFmt(n) {
  if (n == null || n === "") return "—"
  return "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 })
}

function pctFmt(n) {
  if (n == null || n === "") return "—"
  const v = Number(n)
  return (v >= 0 ? "+" : "") + v.toFixed(2) + "%"
}

// ─── Section 1 — Latest signal summary bar ─────────────────────────────────
// Only rendered when a latestSignal is present (comes from WS signal_complete)

function LatestSignalBar({ signal }) {
  const directionCls =
    signal.direction === "BUY"  ? "mp-badge mp-badge-buy"  :
    signal.direction === "SELL" ? "mp-badge mp-badge-sell" :
                                   "mp-badge mp-badge-hold"

  const upside      = signal.upside_pct ?? null
  const upsideColor = upside == null ? "#4A5A78" : upside >= 0 ? "#00E676" : "#FF3D57"

  return (
    <div className="mp-card flex flex-wrap items-center gap-x-3 gap-y-2">

      {/* Direction badge */}
      <span className={directionCls}>{signal.direction}</span>

      {/* Symbol */}
      <span className="font-mono font-bold text-mp-saffron">
        {signal.symbol ?? "—"}
      </span>

      {/* Separator */}
      <span className="text-mp-dim select-none">·</span>

      {/* Current price */}
      <span className="font-mono text-xs text-mp-muted">
        Current:{" "}
        <span className="text-mp-text">{inrFmt(signal.current_price)}</span>
      </span>

      {/* Separator */}
      <span className="text-mp-dim select-none">·</span>

      {/* Target price */}
      <span className="font-mono text-xs text-mp-muted">
        Target:{" "}
        <span className="text-mp-text">{inrFmt(signal.target_price)}</span>
      </span>

      {/* Separator */}
      <span className="text-mp-dim select-none">·</span>

      {/* Upside% */}
      <span
        className="font-mono text-xs font-bold"
        style={{ color: upsideColor }}
      >
        {pctFmt(upside)}
      </span>

      {/* Separator */}
      <span className="text-mp-dim select-none">·</span>

      {/* Confidence */}
      <span className="font-mono text-xs text-mp-muted">
        Confidence:{" "}
        <span className="font-bold text-mp-saffron">
          {signal.confidence != null
            ? `${Number(signal.confidence).toFixed(0)}%`
            : "—"}
        </span>
      </span>

      {/* Separator */}
      <span className="text-mp-dim select-none">·</span>

      {/* Horizon */}
      <span className="font-mono text-xs text-mp-muted">
        {signal.horizon ?? "—"}
      </span>

      {/* SEBI disclaimer — far right, small */}
      <span
        className="ml-auto font-mono text-xs leading-snug text-mp-dim
                   max-w-[220px] text-right"
      >
        ⚠️ Not SEBI-registered. For educational use only.
      </span>
    </div>
  )
}

// ─── Signals page ──────────────────────────────────────────────────────────
// Props:
//   symbol — NSE symbol string or null
export default function SignalsPage({ symbol }) {
  const { token }        = useAuth()
  const { latestSignal } = useWS()
  const { signals }      = useSignals(token, symbol)

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">

      {/* ── Section 1: Latest signal summary bar (conditional) ── */}
      {latestSignal && <LatestSignalBar signal={latestSignal} />}

      {/* ── Section 2: Price chart ── */}
      <PriceChart
        symbol={symbol}
        signals={signals}
        week52={null}
      />

      {/* ── Section 3: Signal history table ── */}
      <div className="mp-card overflow-hidden p-0">
        {/* Card header */}
        <div
          className="flex items-center justify-between border-b
                     border-mp-border px-4 py-3"
        >
          <h2 className="font-mono text-sm font-bold text-mp-text">
            📈 Signal History
          </h2>
          {symbol && (
            <span className="font-mono text-xs text-mp-muted">
              {symbol} · NSE
            </span>
          )}
        </div>

        {/* Table — owns its own padding */}
        <div className="p-4">
          <SignalHistoryTable symbol={symbol} />
        </div>
      </div>

    </div>
  )
}
