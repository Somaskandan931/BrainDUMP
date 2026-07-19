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
        base: "#0A0B0F",
        surface: {
          DEFAULT: "#14161C",
          raised: "#1B1E27",
          overlay: "#20232E",
        },
        hairline: "#262A35",
        ink: {
          DEFAULT: "#E7E9EE",
          muted: "#8A8FA3",
          faint: "#565B6B",
        },
        signal: {
          DEFAULT: "#45D9A6",
          dim: "#1E3A30",
        },
        risk: {
          DEFAULT: "#F5A623",
          dim: "#3A2E14",
        },
        critical: {
          DEFAULT: "#F0554A",
          dim: "#3A1C19",
        },
        primary: {
          DEFAULT: "#7C8BFF",
          dim: "#232748",
          hover: "#93A0FF",
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
