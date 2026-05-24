import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  useCallback,
} from "react"

const WS_BASE = "ws://localhost:8000"
const WSContext = createContext(null)

export function WebSocketProvider({ children }) {
  const [events, setEvents] = useState([])
  const [isConnected, setIsConnected] = useState(false)
  const [latestSignal, setLatestSignal] = useState(null)
  const wsRef = useRef(null)
  const sessionRef = useRef(null)

  const connect = useCallback((sessionId) => {
    // Close any existing connection cleanly
    if (wsRef.current) {
      wsRef.current.close()
    }

    sessionRef.current = sessionId
    setEvents([])
    setLatestSignal(null)

    const ws = new WebSocket(`${WS_BASE}/ws/analyze/${sessionId}`)

    ws.onopen = () => {
      setIsConnected(true)
      console.log("[WS] Connected to session:", sessionId)
    }

    ws.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data)

        console.log("[WS Event]", event.type, event)

        if (event.type === "signal_complete") {
          setLatestSignal(event.signal)
        }

        // Heartbeats don't accumulate in the event log
        if (event.type !== "heartbeat") {
          setEvents((prev) => [...prev, event])
        }

        // Keep-alive pong
        if (event.type === "ping") {
          ws.send("pong")
        }
      } catch (err) {
        console.error("[WS] Parse error:", err)
      }
    }

    ws.onclose = () => {
      setIsConnected(false)
      console.log("[WS] Disconnected")
    }

    ws.onerror = (e) => {
      console.error("[WS] Error:", e)
      setIsConnected(false)
    }

    wsRef.current = ws
  }, [])

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    setIsConnected(false)
    setEvents([])
  }, [])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (wsRef.current) wsRef.current.close()
    }
  }, [])

  return (
    <WSContext.Provider
      value={{
        events,
        isConnected,
        latestSignal,
        connect,
        disconnect,
        sessionId: sessionRef.current,
      }}
    >
      {children}
    </WSContext.Provider>
  )
}

export const useWS = () => useContext(WSContext)
