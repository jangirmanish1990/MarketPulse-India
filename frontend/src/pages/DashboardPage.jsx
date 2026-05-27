import { useState } from "react"
import axios from "axios"
import AgentTrace from "../components/AgentTrace"
import AnalysisTrigger from "../components/AnalysisTrigger"
import SignalsPage from "./SignalsPage"
import CalendarPage from "./CalendarPage"
import { useAuth } from "../context/AuthContext"
import { useWS } from "../context/WebSocketContext"

const API = ""

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

export default function DashboardPage({ symbol, onAnalyze }) {
  console.log("DashboardPage symbol prop:", symbol)
  const { token } = useAuth()
  const { connect, latestSignal } = useWS()

  const [activeTab, setActiveTab] = useState("trace")
  const [sessionId, setSessionId] = useState(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [analyzeError, setAnalyzeError] = useState(null)

  // ── Single trigger function shared by button AND symbol-name click ──────
  const triggerAnalysis = async () => {
    if (!symbol || analyzing) return
    setAnalyzing(true)
    setAnalyzeError(null)
    try {
      const res = await axios.post(
        `${API}/api/analyze/${symbol}`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      )
      const { session_id } = res.data
      setSessionId(session_id)

      // Give the backend 500 ms to reach its retry loop before we connect,
      // so the first broadcast (pipeline_start) is never missed.
      await new Promise((resolve) => setTimeout(resolve, 500))
      connect(session_id)         // open WebSocket stream
    } catch (e) {
      setAnalyzeError(e.response?.data?.message ?? "Analysis failed")
    } finally {
      setAnalyzing(false)
    }
  }

  // ── Reset error + session when the symbol changes ───────────────────────
  // (state from a previous stock doesn't bleed into a freshly selected one)
  const [prevSymbol, setPrevSymbol] = useState(symbol)
  if (symbol !== prevSymbol) {
    setPrevSymbol(symbol)
    setAnalyzeError(null)
    setSessionId(null)
  }

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
              {/* Clicking the symbol name is a shortcut to trigger analysis */}
              <button
                onClick={triggerAnalysis}
                disabled={analyzing}
                title="Click to analyse"
                className={`text-mp-saffron font-bold font-mono text-lg
                           hover:text-mp-saffron/80 transition-colors
                           ${analyzing ? "opacity-60 cursor-not-allowed" : "cursor-pointer"}`}
              >
                {symbol}
              </button>
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

        <AnalysisTrigger
          symbol={symbol}
          loading={analyzing}
          error={analyzeError}
          onTrigger={triggerAnalysis}
        />
      </div>

      {/* ── Tabs ── */}
      <TabBar active={activeTab} onChange={setActiveTab} />

      {/* ── Tab content ── */}
      <div className="flex-1 overflow-hidden">
        {activeTab === "trace" && <AgentTrace symbol={symbol} />}
        {activeTab === "signals" && (
          <SignalsPage symbol={symbol} />
        )}
        {activeTab === "calendar" && <CalendarPage symbol={symbol} onAnalyze={onAnalyze} />}
        {activeTab === "sectors" && (
          <ComingSoon label="Sector comparison coming in Day 20" />
        )}
      </div>
    </div>
  )
}
