import { cn } from "@/lib/format";
import { ReactNode } from "react";

type Tone = "neutral" | "signal" | "risk" | "critical" | "primary";

const TONE_CLASSES: Record<Tone, string> = {
  neutral: "bg-surface-raised text-ink-muted border-hairline",
  signal: "bg-signal-dim text-signal border-signal/20",
  risk: "bg-risk-dim text-risk border-risk/20",
  critical: "bg-critical-dim text-critical border-critical/20",
  primary: "bg-primary-dim text-primary-hover border-primary/20",
};

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium tnum",
        TONE_CLASSES[tone]
      )}
    >
      {children}
    </span>
  );
}
