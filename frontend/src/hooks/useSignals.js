import { useState, useEffect, useCallback } from "react"
import axios from "axios"

const API = ""

export function useSignals(token, symbol = null) {
  const [signals, setSignals] = useState([])
  const [loading, setLoading] = useState(true)
  const [total, setTotal] = useState(0)

  const fetchSignals = useCallback(async (
    limit = 20, offset = 0, direction = null
  ) => {
    if (!token) return
    setLoading(true)
    try {
      const params = new URLSearchParams({ limit, offset })
      if (direction) params.append("direction", direction)
      const url = symbol
        ? `${API}/api/signals/${symbol}?${params}`
        : `${API}/api/signals/recent?${params}`
      const res = await axios.get(url, {
        headers: { Authorization: "Bearer " + token }
      })
      setSignals(res.data.signals || [])
      setTotal(res.data.total || 0)
    } catch (e) {
      console.error("Signals error:", e)
      setSignals([])
    } finally {
      setLoading(false)
    }
  }, [token, symbol])

  useEffect(() => { fetchSignals() }, [fetchSignals])

  return { signals, loading, total, fetchSignals }
}
