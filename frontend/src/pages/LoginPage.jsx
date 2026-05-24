import { useState } from "react"
import { useAuth } from "../context/AuthContext"

export default function LoginPage() {
  const { login, loading, error } = useAuth()
  const [email, setEmail] = useState("manish@marketpulse.in")
  const [password, setPassword] = useState("demo123")

  const handleSubmit = async (e) => {
    e.preventDefault()
    await login(email, password)
  }

  return (
    <div className="min-h-screen bg-mp-bg flex items-center justify-center p-4">

      {/* Subtle saffron grid background */}
      <div
        className="fixed inset-0 opacity-30 pointer-events-none"
        style={{
          backgroundImage: `
            linear-gradient(rgba(255,149,0,0.05) 1px, transparent 1px),
            linear-gradient(90deg, rgba(255,149,0,0.05) 1px, transparent 1px)
          `,
          backgroundSize: "40px 40px",
        }}
      />

      <div className="relative w-full max-w-sm">

        {/* ── Logo ── */}
        <div className="text-center mb-8">
          <div className="text-5xl mb-4">📈</div>
          <h1 className="font-sans font-bold text-3xl text-white">
            Market<span className="text-mp-saffron">Pulse</span>
            <span className="text-mp-muted text-xl ml-2">India</span>
          </h1>
          <p className="text-mp-muted text-sm mt-2 font-mono">
            NSE + BSE Autonomous Intelligence
          </p>
        </div>

        {/* ── Login form ── */}
        <div className="mp-card">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-xs text-mp-muted font-mono block mb-1.5 tracking-wider uppercase">
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mp-input"
                placeholder="you@example.com"
                autoComplete="email"
              />
            </div>
            <div>
              <label className="text-xs text-mp-muted font-mono block mb-1.5 tracking-wider uppercase">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mp-input"
                placeholder="••••••••"
                autoComplete="current-password"
              />
            </div>

            {error && (
              <div
                className="text-mp-red text-xs font-mono
                           bg-red-500/10 border border-red-500/30
                           rounded px-3 py-2"
              >
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="mp-btn-primary w-full py-2.5"
            >
              {loading ? "Signing in…" : "Sign In →"}
            </button>
          </form>

          <div className="mt-4 pt-4 border-t border-mp-border">
            <p className="text-xs text-mp-muted text-center font-mono">
              Demo: manish@marketpulse.in / demo123
            </p>
          </div>
        </div>

        {/* ── SEBI disclaimer ── */}
        <p className="text-center text-xs text-mp-dim mt-6 font-mono leading-relaxed px-4">
          ⚠️ Not a SEBI registered advisor.
          For educational purposes only.
        </p>
      </div>
    </div>
  )
}
