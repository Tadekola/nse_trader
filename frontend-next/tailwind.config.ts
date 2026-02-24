import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        mono: ["JetBrains Mono", "Fira Code", "Consolas", "monospace"],
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      colors: {
        terminal: {
          bg: "#0a0e17",
          surface: "#111827",
          border: "#1e293b",
          "border-bright": "#334155",
          text: "#e2e8f0",
          muted: "#94a3b8",
          dim: "#64748b",
          accent: "#3b82f6",
          green: "#22c55e",
          red: "#ef4444",
          amber: "#f59e0b",
          cyan: "#06b6d4",
        },
      },
    },
  },
  plugins: [],
};

export default config;
