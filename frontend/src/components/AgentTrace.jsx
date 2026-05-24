import { useEffect, useRef } from "react"
import { useWS } from "../context/WebSocketContext"

// ─── Node metadata matching backend NODE_META ─────────────────────────────
// Note: 🇮🇳 replaced with ₹ — flag emojis don't render on Windows

const NODE_META = {
  fetch_market_data: {
    label: "Fetching NSE + yfinance Data",
    color: "#00C4FF",
    icon: "📡",
    bgClass: "border-mp-blue/40 bg-mp-blue/5",
    textClass: "text-mp-blue",
  },
  parse_announcement: {
    label: "Parsing Announcement",
    color: "#A78BFA",
    icon: "📄",
    bgClass: "border-mp-purple/40 bg-mp-purple/5",
    textClass: "text-mp-purple",
  },
  concall_analyzer: {
    label: "Analyzing Concall",
    color: "#818CF8",
    icon: "🎙️",
    bgClass: "border-indigo-500/40 bg-indigo-500/5",
    textClass: "text-indigo-400",
  },
  fetch_india_context: {
    label: "India Market Context",
    color: "#FF9500",
    icon: "₹",            // flag emoji swapped — renders on Windows
    bgClass: "border-mp-saffron/40 bg-mp-saffron/5",
    textClass: "text-mp-saffron",
  },
  retrieve_rag_context: {
    label: "Retrieving Historical Context",
    color: "#FFB800",
    icon: "🔍",
    bgClass: "border-mp-yellow/40 bg-mp-yellow/5",
    textClass: "text-mp-yellow",
  },
  grade_documents: {
    label: "Grading Documents",
    color: "#FFB800",
    icon: "⚖️",
    bgClass: "border-mp-yellow/40 bg-mp-yellow/5",
    textClass: "text-mp-yellow",
  },
  web_search_fallback: {
    label: "Searching Indian News",
    color: "#FB923C",
    icon: "🌐",
    bgClass: "border-orange-500/40 bg-orange-500/5",
    textClass: "text-orange-400",
  },
  generate_analysis: {
    label: "Generating Analysis",
    color: "#00E676",
    icon: "🧠",
    bgClass: "border-mp-green/40 bg-mp-green/5",
    textClass: "text-mp-green",
  },
  score_signal: {
    label: "Scoring Signal",
    color: "#00E676",
    icon: "📈",
    bgClass: "border-mp-green/40 bg-mp-green/5",
    textClass: "text-mp-green",
  },
}

// ─── Animated spinner for running nodes ───────────────────────────────────

function Spinner({ color }) {
  return (
    <div
      className="w-3 h-3 rounded-full border-2 animate-spin flex-shrink-0"
      style={{
        borderColor: `${color}40`,
        borderTopColor: "transparent",
        borderRightColor: color,
      }}
    />
  )
}

// ─── Single node block ─────────────────────────────────────────────────────

function NodeBlock({ event, isRunning }) {
  const meta = NODE_META[event.node] ?? {
    label: event.node,
    color: "#94A3B8",
    icon: "▶",
    bgClass: "border-mp-border bg-mp-surface2",
    textClass: "text-mp-muted",
  }

  const summary = event.summary ?? {}

  // One-line summary per node type — only shown when complete
  const getSummaryLine = () => {
    switch (event.node) {
      case "fetch_market_data":
        if (summary.ltp > 0)
          return `LTP ₹${summary.ltp?.toLocaleString("en-IN")} · Nifty ${summary.nifty?.toLocaleString("en-IN") ?? "—"}`
        return null
      case "parse_announcement":
        if (summary.verdict)
          return `${summary.verdict?.toUpperCase()} · Rev ₹${summary.revenue_cr?.toLocaleString("en-IN") ?? "—"} Cr`
        return null
      case "retrieve_rag_context":
        if (summary.docs_retrieved !== undefined)
          return `${summary.docs_retrieved} docs retrieved`
        return null
      case "grade_documents":
        if (summary.total !== undefined)
          return `${summary.relevant}/${summary.total} relevant · fallback: ${summary.fallback ? "yes ⚠️" : "no ✓"}`
        return null
      case "generate_analysis":
        if (summary.verdict)
          return `${summary.verdict} · ${summary.sector} · sentiment ${summary.sentiment >= 0 ? "+" : ""}${summary.sentiment?.toFixed(2) ?? "—"}`
        return null
      case "score_signal":
        if (summary.direction)
          return `${summary.direction} · ${((summary.confidence ?? 0) * 100).toFixed(0)}% confidence`
        return null
      default:
        return null
    }
  }

  const summaryLine = getSummaryLine()

  // ₹ icon is text, not emoji — render as a small badge instead of emoji span
  const isTextIcon = event.node === "fetch_india_context"

  return (
    <div
      className={`border rounded-lg p-3 animate-fade-in
                  transition-all duration-300 ${meta.bgClass}`}
    >
      {/* Node header row */}
      <div className="flex items-center gap-2">
        {isTextIcon ? (
          <span
            className={`text-sm font-bold font-mono flex-shrink-0 ${meta.textClass}`}
          >
            {meta.icon}
          </span>
        ) : (
          <span className="text-base flex-shrink-0">{meta.icon}</span>
        )}

        <span
          className={`text-xs font-bold font-mono tracking-wider ${meta.textClass}`}
        >
          {meta.label.toUpperCase()}
        </span>

        <div className="flex-1" />

        {isRunning ? (
          <Spinner color={meta.color} />
        ) : (
          <span className={`text-xs ${meta.textClass}`}>✓</span>
        )}

        {event.ist_timestamp && !isRunning && (
          <span className="text-xs text-mp-dim font-mono ml-1">
            {event.ist_timestamp.slice(11, 19)}
          </span>
        )}
      </div>

      {/* Completed summary line */}
      {summaryLine && !isRunning && (
        <div className="mt-1.5 ml-6">
          <span className="text-xs font-mono text-mp-muted">
            → {summaryLine}
          </span>
        </div>
      )}

      {/* Running "processing…" indicator */}
      {isRunning && (
        <div className="mt-1.5 ml-6">
          <span className="text-xs font-mono text-mp-dim animate-pulse">
            processing…
          </span>
        </div>
      )}
    </div>
  )
}

// ─── India context mini-grid (Nifty / USD-INR / Market status) ────────────

function IndiaContextCard({ event }) {
  if (event.node !== "fetch_india_context") return null
  const s = event.summary ?? {}
  if (!s.nifty && !s.fii) return null

  return (
    <div className="ml-6 mt-1 grid grid-cols-3 gap-2">
      {s.nifty && (
        <div className="bg-mp-surface2 rounded px-2 py-1 text-center">
          <div className="text-xs text-mp-muted font-mono">Nifty</div>
          <div className="text-xs font-bold text-mp-text font-mono">
            {s.nifty?.toLocaleString("en-IN")}
          </div>
        </div>
      )}
      {s.usd_inr && (
        <div className="bg-mp-surface2 rounded px-2 py-1 text-center">
          <div className="text-xs text-mp-muted font-mono">USD/INR</div>
          <div className="text-xs font-bold text-mp-text font-mono">
            ₹{s.usd_inr?.toFixed(2)}
          </div>
        </div>
      )}
      {s.market_status && (
        <div className="bg-mp-surface2 rounded px-2 py-1 text-center">
          <div className="text-xs text-mp-muted font-mono">Market</div>
          <div className="text-xs font-bold text-mp-saffron font-mono">
            {s.market_status}
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Signal reveal card ────────────────────────────────────────────────────

function SignalReveal({ signal }) {
  if (!signal) return null

  const direction = signal.direction ?? "HOLD"
  const configs = {
    BUY:  { badge: "mp-badge-buy",  dot: "🟢", glowColor: "#00E676" },
    SELL: { badge: "mp-badge-sell", dot: "🔴", glowColor: "#FF3D57" },
    HOLD: { badge: "mp-badge-hold", dot: "🟡", glowColor: "#FFB800" },
  }
  const cfg = configs[direction] ?? configs.HOLD
  const upside = signal.upside_pct ?? 0

  return (
    <div
      className="border border-mp-green/30 rounded-lg p-4 animate-slide-up shadow-lg"
      style={{ boxShadow: `0 0 24px ${cfg.glowColor}20` }}
    >
      {/* Header */}
      <div className="flex items-center gap-3 mb-3">
        <span className="text-2xl">{cfg.dot}</span>
        <div className="flex items-center gap-2">
          <span className={`mp-badge ${cfg.badge} text-sm`}>
            {direction}
          </span>
          <span className="text-mp-muted text-xs font-mono">
            SIGNAL GENERATED
          </span>
        </div>
        <div className="flex-1" />
        <div className="text-right">
          <div className="text-mp-text font-mono text-sm font-bold">
            {((signal.confidence ?? 0) * 100).toFixed(0)}%
          </div>
          <div className="text-mp-muted text-xs font-mono">confidence</div>
        </div>
      </div>

      {/* Price targets */}
      <div className="grid grid-cols-3 gap-3 mb-3">
        <div className="bg-mp-surface rounded p-2 text-center">
          <div className="text-xs text-mp-muted font-mono mb-0.5">Current</div>
          <div className="text-sm font-bold font-mono text-mp-text">
            ₹{signal.current_price_inr?.toLocaleString("en-IN") ?? "—"}
          </div>
        </div>
        <div className="bg-mp-surface rounded p-2 text-center">
          <div className="text-xs text-mp-muted font-mono mb-0.5">Target</div>
          <div className="text-sm font-bold font-mono text-mp-text">
            ₹{signal.target_price_inr?.toLocaleString("en-IN") ?? "—"}
          </div>
        </div>
        <div className="bg-mp-surface rounded p-2 text-center">
          <div className="text-xs text-mp-muted font-mono mb-0.5">Upside</div>
          <div
            className={`text-sm font-bold font-mono ${
              upside >= 0 ? "text-mp-green" : "text-mp-red"
            }`}
          >
            {upside >= 0 ? "+" : ""}
            {upside?.toFixed(1)}%
          </div>
        </div>
      </div>

      {/* Horizon + date */}
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs text-mp-muted font-mono">
          Horizon: {signal.time_horizon_days} days
        </span>
        <span className="text-xs text-mp-muted font-mono">
          {new Date().toLocaleDateString("en-IN", {
            timeZone: "Asia/Kolkata",
            day: "2-digit",
            month: "short",
            year: "numeric",
          })}
        </span>
      </div>

      {/* Rationale */}
      {signal.rationale && (
        <div className="border-t border-mp-border pt-3">
          <p className="text-xs text-mp-muted font-mono leading-relaxed">
            {signal.rationale}
          </p>
        </div>
      )}

      {/* SEBI disclaimer — mandatory on every signal surface */}
      <div className="border-t border-mp-border mt-3 pt-2">
        <p className="text-xs text-mp-dim font-mono leading-relaxed">
          ⚠️{" "}
          {signal.sebi_disclaimer ??
            "MarketPulse India is not a SEBI-registered investment advisor. Output is for educational/informational purposes only and is not investment advice. Markets carry risk; consult a registered advisor before making decisions."}
        </p>
      </div>
    </div>
  )
}

// ─── Pipeline start banner ─────────────────────────────────────────────────

function PipelineStartBanner({ symbol, announcementType }) {
  return (
    <div className="border border-mp-saffron/30 rounded-lg p-3 bg-mp-saffron/5 animate-fade-in">
      <div className="flex items-center gap-2">
        <span className="text-mp-saffron font-bold font-mono text-sm">
          ▶ PIPELINE STARTED
        </span>
        <span className="text-mp-muted text-xs font-mono">
          {symbol} · {announcementType?.replace(/_/g, " ")}
        </span>
        <div className="flex-1" />
        {/* Staggered pulse dots */}
        <div className="flex gap-1">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="w-1.5 h-1.5 rounded-full bg-mp-saffron animate-pulse"
              style={{ animationDelay: `${i * 0.2}s` }}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

// ─── Main AgentTrace component ─────────────────────────────────────────────

export default function AgentTrace({ symbol }) {
  const { events, isConnected, latestSignal } = useWS()
  const bottomRef = useRef(null)

  // Auto-scroll to bottom as new events arrive
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [events])

  // ── Build a deduplicated ordered list of node events ──────────────────
  // For each node, keep the latest version: running → completed.
  // We walk events in order; when a node_complete arrives we replace
  // the earlier node_start entry in-place so the position is preserved.

  const nodeEvents = []
  const nodeIndexMap = {}  // node name → index in nodeEvents

  events.forEach((evt) => {
    if (evt.type === "node_start") {
      const idx = nodeEvents.length
      nodeIndexMap[evt.node] = idx
      nodeEvents.push({ ...evt, isRunning: true })
    } else if (evt.type === "node_complete") {
      const existing = nodeIndexMap[evt.node]
      if (existing !== undefined) {
        nodeEvents[existing] = { ...evt, isRunning: false }
      } else {
        nodeIndexMap[evt.node] = nodeEvents.length
        nodeEvents.push({ ...evt, isRunning: false })
      }
    }
  })

  const completedCount = nodeEvents.filter((e) => !e.isRunning).length
  const pipelineStart = events.find((e) => e.type === "pipeline_start")
  const hasStarted = !!pipelineStart

  // ── Empty / disconnected state ─────────────────────────────────────────
  if (!hasStarted && !isConnected) {
    return (
      <div className="flex items-center justify-center h-full text-mp-muted">
        <div className="text-center">
          <div className="text-mp-saffron text-3xl mb-3 font-sans font-bold">₹</div>
          <p className="font-mono text-sm">Select a stock from your watchlist</p>
          <p className="font-mono text-xs text-mp-dim mt-1">
            or add a new stock to begin analysis
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col">

      {/* ── Connection status bar ── */}
      <div className="px-4 py-2 border-b border-mp-border flex items-center gap-2 flex-shrink-0">
        <div
          className={`w-2 h-2 rounded-full flex-shrink-0 ${
            isConnected ? "bg-mp-green animate-pulse" : "bg-mp-muted"
          }`}
        />
        <span className="text-xs font-mono text-mp-muted">
          {isConnected ? `Live stream · ${symbol}` : "Connecting…"}
        </span>
        <div className="flex-1" />
        <span className="text-xs font-mono text-mp-dim">
          {completedCount} / 9 nodes
        </span>
      </div>

      {/* ── Scrollable events stream ── */}
      <div className="flex-1 overflow-y-auto p-4 space-y-2">

        {/* Pipeline start banner */}
        {pipelineStart && (
          <PipelineStartBanner
            symbol={pipelineStart.symbol}
            announcementType={pipelineStart.announcement_type}
          />
        )}

        {/* Node blocks */}
        {nodeEvents.map((evt, i) => (
          <div key={`${evt.node}-${i}`}>
            <NodeBlock event={evt} isRunning={evt.isRunning} />
            {/* India context sub-grid only shown when complete */}
            {!evt.isRunning && evt.node === "fetch_india_context" && (
              <IndiaContextCard event={evt} />
            )}
          </div>
        ))}

        {/* Signal reveal — slides in when pipeline finishes */}
        {latestSignal && <SignalReveal signal={latestSignal} />}

        {/* Scroll anchor */}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
