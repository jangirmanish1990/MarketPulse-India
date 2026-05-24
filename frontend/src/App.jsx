import { useState } from "react"
import axios from "axios"
import { AuthProvider, useAuth } from "./context/AuthContext"
import { WebSocketProvider } from "./context/WebSocketContext"
import Header from "./components/Header"
import Sidebar from "./components/Sidebar"
import LoginPage from "./pages/LoginPage"

const API = "http://localhost:8000"

// ─── Analysis panel (placeholder — real trace panel ships in Day 17) ───────

function AnalysisPanel({ sessionId, symbol }) {
  if (!sessionId) {
    return (
      <div className="flex-1 flex items-center justify-center text-mp-muted">
        <div className="text-center animate-fade-in">
          <div className="text-4xl mb-4">🇮🇳</div>
          <p className="font-mono text-sm">Select a stock from your watchlist</p>
          <p className="font-mono text-xs text-mp-dim mt-1">
            or add a new stock to begin analysis
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 p-6 animate-slide-up">
      <div className="mp-card">
        <div className="flex items-center gap-3 mb-4">
          <span className="text-mp-saffron font-bold font-mono text-lg">
            {symbol}
          </span>
          <span className="text-mp-muted text-xs font-mono">
            Analysis in progress…
          </span>
          <span className="w-2 h-2 rounded-full bg-mp-saffron animate-pulse" />
        </div>
        <div className="text-mp-muted text-sm font-mono">
          Session:{" "}
          <span className="text-mp-blue">{sessionId}</span>
        </div>
        <div className="mt-4 text-mp-dim text-xs font-mono border-t border-mp-border pt-4">
          Agent trace + signal output will render here in Day 17.
        </div>
      </div>
    </div>
  )
}

// ─── Authenticated dashboard shell ────────────────────────────────────────

function Dashboard() {
  const { token } = useAuth()
  const [sessionId, setSessionId] = useState(null)
  const [activeSymbol, setActiveSymbol] = useState(null)

  const handleAnalyze = async (symbol) => {
    try {
      const res = await axios.post(
        `${API}/api/analyze/${symbol}`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      )
      setSessionId(res.data.session_id)
      setActiveSymbol(symbol)
    } catch (e) {
      console.error("Analysis trigger error:", e)
    }
  }

  return (
    <div className="flex flex-col h-screen bg-mp-bg">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar onAnalyze={handleAnalyze} />
        <main className="flex-1 overflow-auto flex flex-col">
          <AnalysisPanel sessionId={sessionId} symbol={activeSymbol} />
        </main>
      </div>
    </div>
  )
}

// ─── Route gate (no router needed — single-page state machine) ────────────

function AppContent() {
  const { isAuthenticated } = useAuth()
  return isAuthenticated ? <Dashboard /> : <LoginPage />
}

// ─── Root ──────────────────────────────────────────────────────────────────

export default function App() {
  return (
    <AuthProvider>
      <WebSocketProvider>
        <AppContent />
      </WebSocketProvider>
    </AuthProvider>
  )
}
