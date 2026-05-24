import { useState, useEffect, useCallback } from "react"
import axios from "axios"

const API = "http://localhost:8000"

// ─── Market Summary ────────────────────────────────────────────────────────

export function useMarketData(token) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  const fetch = useCallback(async () => {
    if (!token) return
    try {
      const res = await axios.get(`${API}/api/market/summary`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      setData(res.data)
    } catch (e) {
      console.error("Market data error:", e)
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => {
    fetch()
    // Refresh market summary every 60 seconds
    const interval = setInterval(fetch, 60_000)
    return () => clearInterval(interval)
  }, [fetch])

  return { data, loading, refresh: fetch }
}

// ─── IST Clock (ticks every second) ───────────────────────────────────────

export function useISTClock() {
  const [time, setTime] = useState("")
  const [date, setDate] = useState("")

  useEffect(() => {
    const tick = () => {
      const now = new Date()

      const ist = new Intl.DateTimeFormat("en-IN", {
        timeZone: "Asia/Kolkata",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      }).format(now)

      const dateStr = new Intl.DateTimeFormat("en-IN", {
        timeZone: "Asia/Kolkata",
        weekday: "short",
        day: "2-digit",
        month: "short",
        year: "numeric",
      }).format(now)

      setTime(ist)
      setDate(dateStr)
    }

    tick() // immediate first tick
    const interval = setInterval(tick, 1_000)
    return () => clearInterval(interval)
  }, [])

  return { time, date }
}

// ─── Watchlist ─────────────────────────────────────────────────────────────

export function useWatchlist(token) {
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)

  const fetchWatchlist = useCallback(async () => {
    if (!token) return
    try {
      const res = await axios.get(`${API}/api/watchlist`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      setItems(res.data.items || [])
    } catch (e) {
      console.error("Watchlist error:", e)
    } finally {
      setLoading(false)
    }
  }, [token])

  const addStock = useCallback(
    async (symbol) => {
      try {
        await axios.post(
          `${API}/api/watchlist/${symbol}`,
          {},
          { headers: { Authorization: `Bearer ${token}` } }
        )
        await fetchWatchlist()
        return true
      } catch (e) {
        console.error("Add stock error:", e)
        return false
      }
    },
    [token, fetchWatchlist]
  )

  const removeStock = useCallback(
    async (symbol) => {
      try {
        await axios.delete(`${API}/api/watchlist/${symbol}`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        await fetchWatchlist()
        return true
      } catch (e) {
        console.error("Remove stock error:", e)
        return false
      }
    },
    [token, fetchWatchlist]
  )

  useEffect(() => {
    fetchWatchlist()
  }, [fetchWatchlist])

  return { items, loading, addStock, removeStock, refresh: fetchWatchlist }
}
