import { useState } from "react"
import axios from "axios"
import { useAuth } from "../context/AuthContext"
import { useWS } from "../context/WebSocketContext"

const API = "http://localhost:8000"

export default function AnalysisTrigger({ symbol, onSessionStart }) {
  const { token } = useAuth()
  const { connect } = useWS()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const handleTrigger = async () => {
    if (!symbol) return
    setLoading(true)
    setError(null)

    try {
      const res = await axios.post(
        `${API}/api/analyze/${symbol}`,
        {},
        { headers: { Authorization: `Bearer ${token}` } }
      )

      const { session_id } = res.data

      // Open WebSocket stream before notifying parent
      connect(session_id)

      onSessionStart?.(session_id)
    } catch (e) {
      setError(e.response?.data?.message ?? "Analysis failed")
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={handleTrigger}
        disabled={loading || !symbol}
        className={`mp-btn-primary flex items-center gap-2 ${
          !symbol ? "opacity-50 cursor-not-allowed" : ""
        }`}
      >
        {loading ? (
          <>
            <div
              className="w-3 h-3 border-2 border-black/30
                         border-t-black rounded-full animate-spin"
            />
            Starting…
          </>
        ) : (
          <>
            <span>▶</span>
            Analyse {symbol ?? "—"}
          </>
        )}
      </button>

      {error && (
        <span className="text-mp-red text-xs font-mono">{error}</span>
      )}
    </div>
  )
}
