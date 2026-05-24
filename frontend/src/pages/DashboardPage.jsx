import { useState } from "react"
import AgentTrace from "../components/AgentTrace"
import AnalysisTrigger from "../components/AnalysisTrigger"
import { useWS } from "../context/WebSocketContext"

// ─── Tab definitions ───────────────────────────────────────────────────────

const TABS = [
  { id: "trace",    label: "🔍 Agent Trace" },
  { id: "signals",  label: "📈 Signals" },
  { id: "calendar", label: "📅 Calendar" },
  { id: "sectors",  label: "🏭 Sectors" },
]

// ─── Tab bar ───────────────────────────────────────────────────────────────

function TabBar({ active, onChange }) {
  return (
    <div className="flex border-b border-mp-border px-4 flex-shrink-0">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onChange(tab.id)}
          className={`px-4 py-3 text-xs font-mono font-bold
                     tracking-wider transition-all border-b-2 -mb-px
                     ${
                       active === tab.id
                         ? "border-mp-saffron text-mp-saffron"
                         : "border-transparent text-mp-muted hover:text-mp-text"
                     }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  )
}

// ─── Placeholder for unbuilt tabs ─────────────────────────────────────────

function ComingSoon({ label }) {
  return (
    <div className="flex items-center justify-center h-full text-mp-muted">
      <div className="text-center">
        <div className="text-3xl mb-3">🚧</div>
        <p className="font-mono text-sm">{label}</p>
        <p className="font-mono text-xs text-mp-dim mt-1">Coming in Day 18–19</p>
      </div>
    </div>
  )
}

// ─── Dashboard page ────────────────────────────────────────────────────────

export default function DashboardPage({ symbol }) {
  const [activeTab, setActiveTab] = useState("trace")
  const [sessionId, setSessionId] = useState(null)   // tracked locally for potential future use
  const { latestSignal } = useWS()

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden">

      {/* ── Top bar: symbol + trigger ── */}
      <div
        className="flex items-center justify-between
                   px-4 py-3 border-b border-mp-border
                   bg-mp-surface flex-shrink-0"
      >
        <div className="flex items-center gap-3">
          {symbol ? (
            <>
              <span className="text-mp-saffron font-bold font-mono text-lg">
                {symbol}
              </span>
              <span className="text-mp-muted text-xs font-mono">NSE</span>
              {latestSignal && (
                <span
                  className={`mp-badge ${
                    latestSignal.direction === "BUY"
                      ? "mp-badge-buy"
                      : latestSignal.direction === "SELL"
                      ? "mp-badge-sell"
                      : "mp-badge-hold"
                  }`}
                >
                  {latestSignal.direction}
                </span>
              )}
            </>
          ) : (
            <span className="text-mp-muted text-sm font-mono">
              No stock selected
            </span>
          )}
        </div>

        <AnalysisTrigger symbol={symbol} onSessionStart={setSessionId} />
      </div>

      {/* ── Tabs ── */}
      <TabBar active={activeTab} onChange={setActiveTab} />

      {/* ── Tab content ── */}
      <div className="flex-1 overflow-hidden">
        {activeTab === "trace" && <AgentTrace symbol={symbol} />}
        {activeTab === "signals" && (
          <ComingSoon label="Signal history coming in Day 18" />
        )}
        {activeTab === "calendar" && (
          <ComingSoon label="Results calendar coming in Day 19" />
        )}
        {activeTab === "sectors" && (
          <ComingSoon label="Sector comparison coming in Day 20" />
        )}
      </div>
    </div>
  )
}
