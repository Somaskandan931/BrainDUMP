import { PriorityComponents } from "@/services/types";
import { cn } from "@/lib/format";

interface Row {
  key: keyof PriorityComponents;
  label: string;
  hint: string;
  /** A penalty lowers priority (context switching); the rest raise it. */
  penalty?: boolean;
}

const ROWS: Row[] = [
  { key: "deadline_risk", label: "Deadline pressure", hint: "How close or overdue the deadline is" },
  { key: "importance", label: "Importance", hint: "Your importance rating" },
  { key: "energy_fit", label: "Energy fit", hint: "Match between the task and your usual energy right now" },
  { key: "estimated_hours", label: "Quick-win bonus", hint: "Shorter tasks score slightly higher" },
  {
    key: "context_switch_cost",
    label: "Context-switch penalty",
    hint: "Cost of switching projects — lower is better",
    penalty: true,
  },
];

/** The five raw 0–1 inputs behind a priority score, as labelled bars. */
export function PriorityBreakdown({ components }: { components: PriorityComponents }) {
  return (
    <div className="flex flex-col gap-2">
      {ROWS.map(({ key, label, hint, penalty }) => {
        const value = Math.max(0, Math.min(1, components[key]));
        return (
          <div key={key} title={hint} className="flex items-center gap-3">
            <span className="w-[130px] shrink-0 text-[11px] text-ink-muted">{label}</span>
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-overlay">
              <div
                className={cn("h-full rounded-full", penalty ? "bg-risk" : "bg-primary")}
                style={{ width: `${Math.round(value * 100)}%` }}
              />
            </div>
            <span className="tnum w-9 shrink-0 text-right text-[11px] text-ink">{value.toFixed(2)}</span>
          </div>
        );
      })}
    </div>
  );
}
