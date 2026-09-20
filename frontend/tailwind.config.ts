import type { Config } from "tailwindcss";

// Design system — "instrument panel", not a dashboard template.
// Brain Dump is read at 7am and 11pm on one laptop: dark, quiet,
// legible in low light, numbers read like flight instruments
// (tabular mono), everything else stays out of the way.
const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        base: "rgb(var(--color-base) / <alpha-value>)",
        surface: {
          DEFAULT: "rgb(var(--color-surface) / <alpha-value>)",
          raised: "rgb(var(--color-surface-raised) / <alpha-value>)",
          overlay: "rgb(var(--color-surface-overlay) / <alpha-value>)",
        },
        hairline: "rgb(var(--color-hairline) / <alpha-value>)",
        ink: {
          DEFAULT: "rgb(var(--color-ink) / <alpha-value>)",
          muted: "rgb(var(--color-ink-muted) / <alpha-value>)",
          faint: "rgb(var(--color-ink-faint) / <alpha-value>)",
        },
        signal: {
          DEFAULT: "rgb(var(--color-signal) / <alpha-value>)",
          dim: "rgb(var(--color-signal-dim) / <alpha-value>)",
        },
        risk: {
          DEFAULT: "rgb(var(--color-risk) / <alpha-value>)",
          dim: "rgb(var(--color-risk-dim) / <alpha-value>)",
        },
        critical: {
          DEFAULT: "rgb(var(--color-critical) / <alpha-value>)",
          dim: "rgb(var(--color-critical-dim) / <alpha-value>)",
        },
        primary: {
          DEFAULT: "rgb(var(--color-primary) / <alpha-value>)",
          dim: "rgb(var(--color-primary-dim) / <alpha-value>)",
          hover: "rgb(var(--color-primary-hover) / <alpha-value>)",
        },
      },
      fontFamily: {
        display: ["var(--font-display)", "sans-serif"],
        body: ["var(--font-body)", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
      },
      borderRadius: {
        panel: "10px",
      },
      boxShadow: {
        panel: "0 1px 0 0 rgba(255,255,255,0.02) inset",
      },
      keyframes: {
        sweep: {
          "0%": { transform: "rotate(0deg)" },
          "100%": { transform: "rotate(360deg)" },
        },
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        sweep: "sweep 3s linear infinite",
        "fade-up": "fade-up 0.35s ease-out both",
      },
    },
  },
  plugins: [],
};

export default config;
