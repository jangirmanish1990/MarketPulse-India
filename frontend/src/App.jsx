import { useState } from "react"
import { AuthProvider, useAuth } from "./context/AuthContext"
import { WebSocketProvider } from "./context/WebSocketContext"
import Header from "./components/Header"
import Sidebar from "./components/Sidebar"
import DashboardPage from "./pages/DashboardPage"
import LoginPage from "./pages/LoginPage"

// ─── Authenticated dashboard shell ────────────────────────────────────────

function Dashboard() {
  const [activeSymbol, setActiveSymbol] = useState(null)

  // Clicking a watchlist item sets the active symbol;
  // AnalysisTrigger inside DashboardPage owns the actual API call + WS connect.
  const handleAnalyze = (symbol) => {
    setActiveSymbol(symbol)
  }

  return (
    <div className="flex flex-col h-screen bg-mp-bg overflow-hidden">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar onAnalyze={handleAnalyze} />
        <main className="flex-1 overflow-hidden flex flex-col">
          <DashboardPage symbol={activeSymbol} />
        </main>
      </div>
    </div>
  )
}

// ─── Auth gate ─────────────────────────────────────────────────────────────

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
