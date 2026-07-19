"use client";

/**
 * The signature element: a single instrument-panel dial rather than a
 * generic progress bar. Reused wherever the app shows one real,
 * computed-from-data ratio (today's completion, never a fabricated
 * "AI score" — see app/page.tsx for what feeds this).
 */
export function RadialGauge({
  value,
  size = 132,
  stroke = 10,
  label,
  sublabel,
  tone = "primary",
}: {
  value: number; // 0-100
  size?: number;
  stroke?: number;
  label?: string;
  sublabel?: string;
  tone?: "primary" | "signal" | "risk";
}) {
  const clamped = Math.max(0, Math.min(100, value));
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference * (1 - clamped / 100);
  const colors = {
    primary: "#7C8BFF",
    signal: "#45D9A6",
    risk: "#F5A623",
  };

  return (
    <div className="relative flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="#20232E"
          strokeWidth={stroke}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={colors[tone]}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          style={{ transition: "stroke-dashoffset 0.6s ease-out" }}
        />
      </svg>
      <div className="absolute flex flex-col items-center">
        <span className="tnum font-display text-2xl font-semibold text-ink">
          {Math.round(clamped)}%
        </span>
        <span className="mt-0.5 text-center text-[10px] leading-tight text-ink-faint">
          {sublabel ?? label}
        </span>
      </div>
    </div>
  );
}
