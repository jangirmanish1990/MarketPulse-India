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

// ─── Summary line per node type ───────────────────────────────────────────

function buildSummaryLine(node, summary) {
  switch (node) {
    case "fetch_market_data":
      return summary.ltp > 0
        ? `LTP ₹${summary.ltp?.toLocaleString("en-IN")} · Nifty ${summary.nifty?.toLocaleString("en-IN") ?? "—"}`
        : null
    case "parse_announcement":
      return summary.verdict
        ? `${summary.verdict?.toUpperCase()} · Rev ₹${summary.revenue_cr?.toLocaleString("en-IN") ?? "—"} Cr`
        : null
    case "concall_analyzer":
      if (summary.available === false)
        return "No transcript available — skipped"
      if (summary.tone)
        return `Tone: ${summary.tone} · ${summary.adjustment || "maintain"}`
      return null
    case "retrieve_rag_context":
      return summary.docs_retrieved !== undefined
        ? `${summary.docs_retrieved} docs retrieved`
        : null
    case "grade_documents":
      return summary.total !== undefined
        ? `${summary.relevant}/${summary.total} relevant · fallback: ${summary.fallback ? "yes ⚠️" : "no ✓"}`
        : null
    case "generate_analysis":
      return summary.verdict
        ? `${summary.verdict} · ${summary.sector} outlook`
        : null
    case "score_signal":
      return summary.direction
        ? `${summary.direction} · ${((summary.confidence ?? 0) * 100).toFixed(0)}% confidence`
        : null
    default:
      return null
  }
}

// ─── Single event block — handles all event types ─────────────────────────

function EventBlock({ event }) {
  const meta = NODE_META[event.node] ?? {
    label: event.node || event.type,
    color: "#94A3B8",
    icon: "▶",
    bgClass: "border-mp-border bg-mp-surface2",
    textClass: "text-mp-muted",
  }

  if (event.type === "pipeline_start") {
    return (
      <div className="border border-mp-saffron/30 rounded-lg p-3 bg-mp-saffron/5 animate-fade-in">
        <div className="flex items-center gap-2">
          <span className="text-mp-saffron font-bold font-mono text-xs">
            ▶ PIPELINE STARTED · {event.symbol}
          </span>
          <div className="flex gap-1 ml-auto">
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

  if (event.type === "node_start") {
    return (
      <div className={`border rounded-lg p-3 animate-fade-in ${meta.bgClass}`}>
        <div className="flex items-center gap-2">
          <span className="text-base flex-shrink-0">{meta.icon}</span>
          <span className={`text-xs font-bold font-mono tracking-wider ${meta.textClass}`}>
            {meta.label.toUpperCase()}
          </span>
          <div className="flex-1" />
          <Spinner color={meta.color} />
          <span className="text-xs text-mp-dim font-mono">
            {event.ist_timestamp?.slice(11, 19)}
          </span>
        </div>
        <div className="mt-1 ml-6">
          <span className="text-xs font-mono text-mp-dim animate-pulse">
            processing...
          </span>
        </div>
      </div>
    )
  }

  if (event.type === "node_complete") {
    const summary = event.summary ?? {}
    const summaryLine = buildSummaryLine(event.node, summary)
    return (
      <div className={`border rounded-lg p-3 animate-fade-in ${meta.bgClass}`}>
        <div className="flex items-center gap-2">
          <span className="text-base flex-shrink-0">{meta.icon}</span>
          <span className={`text-xs font-bold font-mono tracking-wider ${meta.textClass}`}>
            {meta.label.toUpperCase()}
          </span>
          <div className="flex-1" />
          <span className={`text-xs ${meta.textClass}`}>✓</span>
          <span className="text-xs text-mp-dim font-mono">
            {event.ist_timestamp?.slice(11, 19)}
          </span>
        </div>
        {summaryLine && (
          <div className="mt-1 ml-6">
            <span className="text-xs font-mono text-mp-muted">
              → {summaryLine}
            </span>
          </div>
        )}
      </div>
    )
  }

  if (event.type === "tool_call") {
    return (
      <div className="ml-4 border-l-2 border-mp-dim pl-3 py-1 animate-fade-in">
        <span className="text-xs font-mono text-mp-dim">
          🔧 {event.tool || event.message}
        </span>
      </div>
    )
  }

  if (event.type === "error") {
    return (
      <div className="border border-mp-red/30 rounded-lg p-3 bg-mp-red/5 animate-fade-in">
        <span className="text-xs font-mono text-mp-red">
          ❌ {event.error || event.message}
        </span>
      </div>
    )
  }

  return null
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

// ─── Main AgentTrace component ─────────────────────────────────────────────

export default function AgentTrace({ symbol }) {
  const { events, isConnected, latestSignal } = useWS()
  const bottomRef = useRef(null)

  // Auto-scroll to latest event
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [events])

  // Simple: render all meaningful events in arrival order.
  // No dedup/reorder — what arrives is what shows.
  const displayEvents = events.filter((e) =>
    ["pipeline_start", "node_start", "node_complete", "tool_call", "error"].includes(e.type)
  )

  const completedCount = events.filter((e) => e.type === "node_complete").length
  const pipelineStarted = events.some((e) => e.type === "pipeline_start")

  // ── Empty / disconnected state ─────────────────────────────────────────
  if (!pipelineStarted && !isConnected) {
    return (
      <div className="flex items-center justify-center h-full text-mp-muted">
        <div className="text-center">
          <div className="text-mp-saffron text-4xl mb-3 font-bold">₹</div>
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
          {isConnected ? `Live stream · ${symbol}` : "Connecting..."}
        </span>
        <div className="flex-1" />
        <span className="text-xs font-mono text-mp-dim">
          {completedCount} / 9 nodes
        </span>
      </div>

      {/* ── Scrollable events stream ── */}
      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        {displayEvents.map((evt, i) => (
          <EventBlock key={i} event={evt} />
        ))}
        {latestSignal && <SignalReveal signal={latestSignal} />}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
