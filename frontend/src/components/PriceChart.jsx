import { useState, useMemo } from "react"
import {
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
} from "recharts"

// ─── Design tokens (raw hex for use inside Recharts SVG props) ─────────────
const C = {
  saffron:  "#FF9500",
  green:    "#00E676",
  red:      "#FF3D57",
  yellow:   "#FFB800",
  border:   "#1A2A45",
  muted:    "#4A5A78",
  bg:       "#04080F",
  surface:  "#080E1A",
  surface2: "#0C1424",
  text:     "#C8D8F0",
}

const SIGNAL_COLOR = {
  BUY:  C.green,
  SELL: C.red,
  HOLD: C.yellow,
}

const PERIODS = [
  { key: "1M", days: 22  },
  { key: "3M", days: 66  },
  { key: "6M", days: 130 },
  { key: "1Y", days: 252 },
]

// ─── Deterministic seeded PRNG (mulberry32) ────────────────────────────────
function mulberry32(seed) {
  return () => {
    seed |= 0
    seed = (seed + 0x6d2b79f5) | 0
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

function strHash(s) {
  let h = 5381
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) + h) ^ s.charCodeAt(i)
  }
  return h >>> 0
}

// ─── Generate 252 trading days of mock OHLCV ending today ─────────────────
function generateMockData(symbol) {
  const rand = mulberry32(strHash(symbol || "DEFAULT"))

  // Walk back from today collecting trading days (skip Sat/Sun)
  const tradingDays = []
  const cursor = new Date()
  while (tradingDays.length < 252) {
    const dow = cursor.getDay()
    if (dow !== 0 && dow !== 6) {
      tradingDays.unshift(new Date(cursor))
    }
    cursor.setDate(cursor.getDate() - 1)
  }

  let price = 1200
  return tradingDays.map((d) => {
    // ±2% random walk
    const delta = (rand() - 0.5) * 0.04
    price = Math.max(50, price * (1 + delta))
    price = Math.round(price * 100) / 100

    const volume = Math.round(rand() * 4_500_000 + 500_000)

    // "15 Apr" — display label
    const label = d.toLocaleDateString("en-IN", {
      day:      "2-digit",
      month:    "short",
      timeZone: "Asia/Kolkata",
    })

    // "YYYY-MM-DD" — used to match signals by date
    const iso = d.toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" })

    return { date: label, iso, price, volume }
  })
}

// ─── Indian rupee formatter ────────────────────────────────────────────────
function inrFmt(n) {
  return "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 2 })
}

// ─── Custom dark tooltip ───────────────────────────────────────────────────
function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null

  const priceEntry  = payload.find((p) => p.dataKey === "price")
  const volumeEntry = payload.find((p) => p.dataKey === "volume")
  const sig         = payload[0]?.payload?.signal

  return (
    <div
      className="rounded border border-mp-border bg-mp-surface2
                 px-3 py-2 font-mono text-xs shadow-lg"
    >
      <p className="mb-1 text-mp-muted">{label}</p>
      {priceEntry && (
        <p style={{ color: C.saffron }} className="font-bold">
          {inrFmt(priceEntry.value)}
        </p>
      )}
      {volumeEntry && (
        <p className="text-mp-muted">
          Vol:{" "}
          {Number(volumeEntry.value).toLocaleString("en-IN")}
        </p>
      )}
      {sig && (
        <p
          className="mt-1 font-bold tracking-wider"
          style={{ color: SIGNAL_COLOR[sig] }}
        >
          ● {sig}
        </p>
      )}
    </div>
  )
}

// ─── Custom dot — renders a colored circle only on signal dates ────────────
function SignalDot({ cx, cy, payload }) {
  const color = SIGNAL_COLOR[payload?.signal]
  if (!cx || !cy || !color) return null
  return (
    <circle
      cx={cx}
      cy={cy}
      r={5}
      fill={color}
      stroke={C.bg}
      strokeWidth={1.5}
    />
  )
}

// ─── 52-week range bar shown above the chart ───────────────────────────────
function Week52Bar({ week52, currentPrice }) {
  const { high, low } = week52
  const range = high - low
  const pct   = range > 0 ? Math.min(100, Math.max(0, ((currentPrice - low) / range) * 100)) : 50

  return (
    <div className="mb-4 px-1">
      <div className="flex justify-between mb-1 text-xs font-mono">
        <span style={{ color: C.red }}>52W L: {inrFmt(low)}</span>
        <span className="text-mp-muted">Now: {inrFmt(currentPrice)}</span>
        <span style={{ color: C.green }}>52W H: {inrFmt(high)}</span>
      </div>
      <div className="relative h-1.5 rounded-full bg-mp-border overflow-visible">
        {/* Gradient fill up to current position */}
        <div
          className="absolute h-full rounded-full"
          style={{
            width:      `${pct}%`,
            background: `linear-gradient(to right, ${C.red}, ${C.yellow}, ${C.green})`,
          }}
        />
        {/* Thumb */}
        <div
          className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2
                     w-2.5 h-2.5 rounded-full border-2 bg-mp-surface"
          style={{
            left:        `${pct}%`,
            borderColor: C.saffron,
          }}
        />
      </div>
    </div>
  )
}

// ─── Custom legend below chart ─────────────────────────────────────────────
function ChartLegend() {
  return (
    <div className="mt-3 flex flex-wrap items-center gap-4 px-1">
      {/* Price line */}
      <span className="flex items-center gap-1.5 text-xs font-mono text-mp-muted">
        <span
          className="inline-block h-0.5 w-6 rounded"
          style={{ background: C.saffron }}
        />
        Price
      </span>

      {/* Signal dots */}
      {[
        { label: "BUY",  color: C.green  },
        { label: "SELL", color: C.red    },
        { label: "HOLD", color: C.yellow },
      ].map(({ label, color }) => (
        <span
          key={label}
          className="flex items-center gap-1.5 text-xs font-mono text-mp-muted"
        >
          <span
            className="inline-block h-2.5 w-2.5 rounded-full"
            style={{ background: color }}
          />
          {label}
        </span>
      ))}
    </div>
  )
}

// ─── Main component ────────────────────────────────────────────────────────
// Props:
//   symbol   — NSE symbol string
//   signals  — array of signal objects with { direction, created_at|date }
//   week52   — { high: number, low: number } or null
export default function PriceChart({ symbol, signals = [], week52 = null }) {
  const [period, setPeriod] = useState("3M")

  // 252 days of mock data, stable per symbol
  const allData = useMemo(() => generateMockData(symbol), [symbol])

  // Slice to selected period and overlay signal markers
  const data = useMemo(() => {
    // Build date → direction lookup from signals prop
    const sigMap = {}
    for (const s of signals) {
      const raw = s.created_at || s.date || ""
      if (raw) sigMap[raw.slice(0, 10)] = s.direction
    }

    const days = PERIODS.find((p) => p.key === period)?.days ?? 66
    return allData.slice(-days).map((d) => ({
      ...d,
      signal: sigMap[d.iso] ?? null,
    }))
  }, [allData, period, signals])

  const currentPrice = data.at(-1)?.price ?? 0
  const maxVol       = Math.max(...data.map((d) => d.volume))
  // Show ~6 x-axis ticks regardless of period
  const tickInterval = Math.max(1, Math.floor(data.length / 6))

  return (
    <div className="mp-card">

      {/* ── Header: symbol name + period selector ── */}
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-mono text-sm font-bold text-mp-text">
          {symbol ?? "—"}{" "}
          <span className="font-normal text-mp-muted">Price</span>
        </h3>

        <div className="flex gap-1">
          {PERIODS.map(({ key }) => (
            <button
              key={key}
              onClick={() => setPeriod(key)}
              className={`rounded px-2.5 py-1 text-xs font-mono font-bold
                         transition-all
                         ${period === key
                           ? "bg-mp-saffron text-black"
                           : "bg-mp-border text-mp-muted hover:text-mp-text"
                         }`}
            >
              {key}
            </button>
          ))}
        </div>
      </div>

      {/* ── 52-week range bar ── */}
      {week52 && (
        <Week52Bar week52={week52} currentPrice={currentPrice} />
      )}

      {/* ── Recharts ComposedChart ── */}
      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart
          data={data}
          margin={{ top: 8, right: 16, left: 0, bottom: 0 }}
        >
          <CartesianGrid
            strokeDasharray="3 3"
            stroke={C.border}
            vertical={false}
          />

          <XAxis
            dataKey="date"
            interval={tickInterval}
            tick={{
              fill:       C.muted,
              fontSize:   10,
              fontFamily: "JetBrains Mono, monospace",
            }}
            tickLine={false}
            axisLine={{ stroke: C.border }}
          />

          {/* Left Y axis — price */}
          <YAxis
            yAxisId="price"
            orientation="left"
            domain={["auto", "auto"]}
            tick={{
              fill:       C.muted,
              fontSize:   10,
              fontFamily: "JetBrains Mono, monospace",
            }}
            tickLine={false}
            axisLine={false}
            tickFormatter={inrFmt}
            width={76}
          />

          {/* Right Y axis — volume (hidden; only drives bar scale) */}
          <YAxis
            yAxisId="volume"
            orientation="right"
            domain={[0, maxVol * 4]}  // bars fill bottom ~25% of canvas
            hide
          />

          <Tooltip content={<ChartTooltip />} />

          {/* 52W reference lines */}
          {week52 && (
            <>
              <ReferenceLine
                yAxisId="price"
                y={week52.high}
                stroke={C.green}
                strokeDasharray="5 3"
                label={{
                  value:      "52W H",
                  position:   "insideTopRight",
                  fill:       C.green,
                  fontSize:   9,
                  fontFamily: "JetBrains Mono, monospace",
                }}
              />
              <ReferenceLine
                yAxisId="price"
                y={week52.low}
                stroke={C.red}
                strokeDasharray="5 3"
                label={{
                  value:      "52W L",
                  position:   "insideBottomRight",
                  fill:       C.red,
                  fontSize:   9,
                  fontFamily: "JetBrains Mono, monospace",
                }}
              />
            </>
          )}

          {/* Volume bars — dark navy, bottom quarter */}
          <Bar
            yAxisId="volume"
            dataKey="volume"
            fill={C.border}
            opacity={0.75}
            isAnimationActive={false}
            radius={[1, 1, 0, 0]}
          />

          {/* Price line — saffron, with signal dots */}
          <Line
            yAxisId="price"
            type="monotone"
            dataKey="price"
            stroke={C.saffron}
            strokeWidth={1.5}
            dot={(dotProps) => <SignalDot {...dotProps} />}
            activeDot={{
              r:           4,
              fill:        C.saffron,
              stroke:      C.bg,
              strokeWidth: 2,
            }}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>

      {/* ── Legend ── */}
      <ChartLegend />

      {/* ── SEBI disclaimer (mandatory — component renders signal markers) ── */}
      <p
        className="mt-3 border-t border-mp-border pt-2
                   font-mono text-xs leading-relaxed text-mp-dim"
      >
        ⚠️ MarketPulse India is not a SEBI-registered investment advisor.
        Output is for educational/informational purposes only and is not
        investment advice. Markets carry risk; consult a registered advisor
        before making decisions.
      </p>
    </div>
  )
}
