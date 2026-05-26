import { useState, useEffect, useMemo } from "react"
import { useAuth }    from "../context/AuthContext"
import { useSignals } from "../hooks/useSignals"

const PAGE_SIZE = 10

// ─── Helpers ───────────────────────────────────────────────────────────────

function inrFmt(n) {
  if (n == null || n === "") return "—"
  return "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 })
}

function pctFmt(n) {
  if (n == null || n === "") return "—"
  const v = Number(n)
  return (v >= 0 ? "+" : "") + v.toFixed(2) + "%"
}

// Value extractor used for client-side sort
function getSortValue(sig, col) {
  switch (col) {
    case "date":       return sig.created_ist || sig.created_at || ""
    case "symbol":     return (sig.symbol || "").toUpperCase()
    case "direction":  return sig.direction || ""
    case "confidence": return sig.confidence  ?? 0
    case "upside":     return sig.upside_pct  ?? 0
    case "target":     return sig.target_price ?? 0
    default:           return ""
  }
}

// Build a CSV blob and trigger a browser download
function exportCSV(signals) {
  const headers = [
    "Date", "Symbol", "Direction", "Confidence%",
    "Current Price", "Target Price", "Upside%", "Horizon", "Rationale",
  ]
  const rows = signals.map((s) => [
    (s.created_ist || s.created_at || "").slice(0, 10),
    s.symbol   ?? "",
    s.direction ?? "",
    s.confidence   != null ? Number(s.confidence).toFixed(1)    : "",
    s.current_price != null ? Number(s.current_price).toFixed(2) : "",
    s.target_price  != null ? Number(s.target_price).toFixed(2)  : "",
    s.upside_pct    != null ? Number(s.upside_pct).toFixed(2)    : "",
    s.horizon  ?? "",
    `"${(s.rationale || "").replace(/"/g, '""')}"`,
  ])
  const csv  = [headers.join(","), ...rows.map((r) => r.join(","))].join("\r\n")
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" })
  const url  = URL.createObjectURL(blob)
  const a    = document.createElement("a")
  a.href     = url
  a.download = `marketpulse_signals_${new Date().toLocaleDateString("en-CA")}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

// ─── Sub-components ────────────────────────────────────────────────────────

function DirectionBadge({ direction }) {
  const cls =
    direction === "BUY"  ? "mp-badge mp-badge-buy"  :
    direction === "SELL" ? "mp-badge mp-badge-sell" :
    direction === "HOLD" ? "mp-badge mp-badge-hold" :
    "mp-badge bg-mp-border text-mp-muted"
  return <span className={cls}>{direction ?? "—"}</span>
}

function ConfidenceBar({ value }) {
  const pct   = Math.min(100, Math.max(0, value ?? 0))
  const color =
    pct >= 80 ? "#00E676" :
    pct >= 60 ? "#FFB800" :
               "#FF3D57"
  return (
    <div className="flex min-w-[96px] items-center gap-2">
      <div className="relative h-1.5 w-14 overflow-hidden rounded-full bg-mp-border">
        <div
          className="absolute inset-y-0 left-0 rounded-full"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span className="font-mono text-xs" style={{ color }}>
        {pct.toFixed(0)}%
      </span>
    </div>
  )
}

// Sortable column header
function SortTh({ col, label, sort, onSort }) {
  const active = sort.col === col
  return (
    <th
      className="cursor-pointer select-none whitespace-nowrap px-3 py-2.5
                 text-left text-xs font-mono font-bold tracking-wider
                 text-mp-muted transition-colors hover:text-mp-text"
      onClick={() => onSort(col)}
    >
      {label}
      <span className="ml-1 opacity-50">
        {active ? (sort.dir === "asc" ? "▲" : "▼") : "↕"}
      </span>
    </th>
  )
}

// Direction filter pill button
function FilterBtn({ value, active, onClick }) {
  if (value === "ALL") {
    return (
      <button
        onClick={onClick}
        className={`rounded px-3 py-1 text-xs font-mono font-bold
                   tracking-wider uppercase transition-all
                   ${active
                     ? "bg-mp-border text-mp-text"
                     : "border border-mp-border/50 text-mp-dim hover:text-mp-muted"
                   }`}
      >
        ALL
      </button>
    )
  }

  // Active: use the badge colour style; inactive: ghost pill
  const activeCls =
    value === "BUY"  ? "mp-badge mp-badge-buy  cursor-pointer" :
    value === "SELL" ? "mp-badge mp-badge-sell cursor-pointer" :
                       "mp-badge mp-badge-hold cursor-pointer"

  const inactiveCls =
    "rounded border border-mp-border/50 px-2 py-0.5 text-xs font-mono " +
    "font-bold tracking-wider uppercase text-mp-dim " +
    "hover:text-mp-muted transition-all cursor-pointer"

  return (
    <button onClick={onClick} className={active ? activeCls : inactiveCls}>
      {value}
    </button>
  )
}

// ─── Main component ────────────────────────────────────────────────────────
// Props:
//   symbol  — optional NSE symbol; when given, scopes table to that ticker
export default function SignalHistoryTable({ symbol = null }) {
  const { token }                                  = useAuth()
  const { signals, loading, total, fetchSignals }  = useSignals(token, symbol)

  const [filter, setFilter] = useState("ALL")
  const [page,   setPage]   = useState(0)
  const [sort,   setSort]   = useState({ col: "date", dir: "desc" })

  // Re-fetch from API whenever filter or page changes
  useEffect(() => {
    fetchSignals(
      PAGE_SIZE,
      page * PAGE_SIZE,
      filter === "ALL" ? null : filter,
    )
  }, [filter, page, fetchSignals])

  // Reset to page 0 whenever the filter changes
  const handleFilter = (f) => {
    setFilter(f)
    setPage(0)
  }

  // Toggle sort: same column flips direction; new column defaults to desc
  const toggleSort = (col) =>
    setSort((prev) =>
      prev.col === col
        ? { col, dir: prev.dir === "asc" ? "desc" : "asc" }
        : { col, dir: "desc" },
    )

  // Client-side sort on the current page of data
  const sorted = useMemo(() => {
    if (!signals.length) return signals
    return [...signals].sort((a, b) => {
      const av = getSortValue(a, sort.col)
      const bv = getSortValue(b, sort.col)
      const cmp = av < bv ? -1 : av > bv ? 1 : 0
      return sort.dir === "asc" ? cmp : -cmp
    })
  }, [signals, sort])

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="mp-card flex flex-col gap-3">

      {/* ── Toolbar ─────────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-2">

        {/* Filter pills + count */}
        <div className="flex items-center gap-1.5">
          {["ALL", "BUY", "HOLD", "SELL"].map((f) => (
            <FilterBtn
              key={f}
              value={f}
              active={filter === f}
              onClick={() => handleFilter(f)}
            />
          ))}
          {!loading && (
            <span className="ml-2 font-mono text-xs text-mp-dim">
              {total} signal{total !== 1 ? "s" : ""}
            </span>
          )}
        </div>

        {/* Export CSV */}
        <button
          onClick={() => exportCSV(signals)}
          disabled={signals.length === 0}
          className="flex items-center gap-1.5 rounded border border-mp-border
                     px-3 py-1.5 font-mono text-xs font-bold text-mp-muted
                     transition-all hover:border-mp-saffron hover:text-mp-saffron
                     disabled:cursor-not-allowed disabled:opacity-30"
        >
          ↓ Export CSV
        </button>
      </div>

      {/* ── Table ───────────────────────────────────────────────────────── */}
      <div className="overflow-x-auto rounded border border-mp-border">
        <table className="w-full border-collapse text-xs font-mono">

          {/* Sticky header */}
          <thead>
            <tr className="sticky top-0 border-b border-mp-border bg-mp-surface">
              <SortTh col="date"       label="Date"       sort={sort} onSort={toggleSort} />
              <SortTh col="symbol"     label="Symbol"     sort={sort} onSort={toggleSort} />
              <SortTh col="direction"  label="Direction"  sort={sort} onSort={toggleSort} />
              <SortTh col="confidence" label="Confidence" sort={sort} onSort={toggleSort} />
              <SortTh col="upside"     label="Upside%"    sort={sort} onSort={toggleSort} />
              {/* Target and Rationale are display-only, not sortable */}
              <th className="px-3 py-2.5 text-left text-xs font-bold
                             tracking-wider text-mp-muted">
                Target
              </th>
              <th className="px-3 py-2.5 text-left text-xs font-bold
                             tracking-wider text-mp-muted">
                Rationale
              </th>
            </tr>
          </thead>

          <tbody>

            {/* Loading state */}
            {loading && (
              <tr>
                <td
                  colSpan={7}
                  className="px-4 py-10 text-center font-mono text-xs text-mp-muted"
                >
                  <span className="animate-pulse">Loading signals…</span>
                </td>
              </tr>
            )}

            {/* Empty state */}
            {!loading && sorted.length === 0 && (
              <tr>
                <td
                  colSpan={7}
                  className="px-4 py-10 text-center font-mono text-xs text-mp-muted"
                >
                  <div className="flex flex-col items-center gap-2">
                    <span className="text-2xl">📭</span>
                    <span>No signals yet. Run an analysis.</span>
                  </div>
                </td>
              </tr>
            )}

            {/* Data rows */}
            {!loading &&
              sorted.map((sig, i) => {
                const upside      = sig.upside_pct ?? null
                const upsideColor =
                  upside == null ? "#4A5A78" :
                  upside >= 0    ? "#00E676" : "#FF3D57"

                return (
                  <tr
                    key={sig.id ?? `${sig.symbol}-${i}`}
                    className="border-b border-mp-border/50
                               transition-colors hover:bg-mp-surface2"
                  >
                    {/* Date — first 10 chars of created_ist */}
                    <td className="whitespace-nowrap px-3 py-2.5 text-mp-muted">
                      {(sig.created_ist || sig.created_at || "—").slice(0, 10)}
                    </td>

                    {/* Symbol — saffron bold */}
                    <td className="whitespace-nowrap px-3 py-2.5
                                   font-bold text-mp-saffron">
                      {sig.symbol ?? "—"}
                    </td>

                    {/* Direction badge */}
                    <td className="px-3 py-2.5">
                      <DirectionBadge direction={sig.direction} />
                    </td>

                    {/* Confidence — progress bar + colour-coded % */}
                    <td className="px-3 py-2.5">
                      <ConfidenceBar value={sig.confidence} />
                    </td>

                    {/* Upside% — green if positive, red if negative */}
                    <td
                      className="whitespace-nowrap px-3 py-2.5 font-bold"
                      style={{ color: upsideColor }}
                    >
                      {pctFmt(upside)}
                    </td>

                    {/* Target price — Indian rupee format */}
                    <td className="whitespace-nowrap px-3 py-2.5 text-mp-text">
                      {inrFmt(sig.target_price)}
                    </td>

                    {/* Rationale — truncated */}
                    <td
                      className="max-w-xs truncate px-3 py-2.5 text-mp-muted"
                      title={sig.rationale ?? ""}
                    >
                      {sig.rationale ?? "—"}
                    </td>
                  </tr>
                )
              })}
          </tbody>
        </table>
      </div>

      {/* ── Pagination ──────────────────────────────────────────────────── */}
      {!loading && total > 0 && (
        <div className="flex items-center justify-between">
          <span className="font-mono text-xs text-mp-muted">
            Page {page + 1} of {totalPages}
            <span className="ml-1 text-mp-dim">· {total} total</span>
          </span>

          <div className="flex gap-1.5">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="rounded border border-mp-border px-3 py-1
                         font-mono text-xs text-mp-muted transition-all
                         hover:border-mp-saffron hover:text-mp-saffron
                         disabled:cursor-not-allowed disabled:opacity-30"
            >
              ← Prev
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={page >= totalPages - 1}
              className="rounded border border-mp-border px-3 py-1
                         font-mono text-xs text-mp-muted transition-all
                         hover:border-mp-saffron hover:text-mp-saffron
                         disabled:cursor-not-allowed disabled:opacity-30"
            >
              Next →
            </button>
          </div>
        </div>
      )}

      {/* ── SEBI disclaimer (mandatory — table renders BUY/SELL/HOLD signals) ── */}
      <p className="border-t border-mp-border pt-2 font-mono
                    text-xs leading-relaxed text-mp-dim">
        ⚠️ MarketPulse India is not a SEBI-registered investment advisor.
        Output is for educational/informational purposes only and is not
        investment advice. Markets carry risk; consult a registered advisor
        before making decisions.
      </p>
    </div>
  )
}
