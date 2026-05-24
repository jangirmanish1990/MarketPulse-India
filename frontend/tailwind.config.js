/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // Core backgrounds
        "mp-bg":       "#04080F",
        "mp-surface":  "#080E1A",
        "mp-surface2": "#0C1424",
        "mp-border":   "#1A2A45",
        // Accents
        "mp-saffron":  "#FF9500",
        "mp-blue":     "#00C4FF",
        "mp-green":    "#00E676",
        "mp-red":      "#FF3D57",
        "mp-yellow":   "#FFB800",
        "mp-purple":   "#A78BFA",
        // Text
        "mp-text":     "#C8D8F0",
        "mp-muted":    "#4A5A78",
        "mp-dim":      "#2A3A58",
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
        sans: ["Outfit", "Inter", "sans-serif"],
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "fade-in":    "fadeIn 0.3s ease-out",
        "slide-up":   "slideUp 0.3s ease-out",
        "ticker":     "ticker 30s linear infinite",
      },
      keyframes: {
        fadeIn: {
          "0%":   { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%":   { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        ticker: {
          "0%":   { transform: "translateX(0)" },
          "100%": { transform: "translateX(-50%)" },
        },
      },
    },
  },
  plugins: [],
}
