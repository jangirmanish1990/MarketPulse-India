// Pure UI button — all API/WS logic lives in DashboardPage.
// Props:
//   symbol     — NSE symbol string (or null when nothing selected)
//   loading    — true while POST /analyze is in flight
//   error      — error message string or null
//   onTrigger  — async function to call on click

export default function AnalysisTrigger({ symbol, loading, error, onTrigger }) {
  const disabled = loading || !symbol

  return (
    <div className="flex items-center gap-3">
      <button
        onClick={onTrigger}
        disabled={disabled}
        className={`mp-btn-primary flex items-center gap-2 ${
          disabled ? "opacity-50 cursor-not-allowed" : ""
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
            {symbol ? `Analyse ${symbol}` : "Analyse —"}
          </>
        )}
      </button>

      {error && (
        <span className="text-mp-red text-xs font-mono">{error}</span>
      )}
    </div>
  )
}
