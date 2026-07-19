"use client";

import { Check } from "lucide-react";
import { Task } from "@/services/types";
import { Badge } from "@/components/ui/Badge";
import { cn, formatDeadline, formatHours } from "@/lib/format";

const IMPORTANCE_TONE = {
  critical: "critical",
  high: "risk",
  medium: "primary",
  low: "neutral",
} as const;

export function TaskRow({
  task,
  onComplete,
  dense = false,
}: {
  task: Task;
  onComplete?: (id: number) => void;
  dense?: boolean;
}) {
  const deadline = formatDeadline(task.deadline);
  const done = task.status === "completed";

  return (
    <div
      className={cn(
        "group flex items-center gap-3 rounded-md border border-transparent px-2 py-2 hover:border-hairline hover:bg-surface-raised",
        dense && "py-1.5"
      )}
    >
      <button
        onClick={() => onComplete?.(task.id)}
        disabled={!onComplete || done}
        aria-label={done ? "Completed" : `Mark "${task.title}" complete`}
        className={cn(
          "flex h-5 w-5 shrink-0 items-center justify-center rounded-full border transition-colors",
          done
            ? "border-signal bg-signal-dim text-signal"
            : "border-hairline text-transparent hover:border-primary hover:text-primary"
        )}
      >
        <Check size={12} strokeWidth={3} />
      </button>

      <div className="min-w-0 flex-1">
        <p className={cn("truncate text-[13px]", done ? "text-ink-faint line-through" : "text-ink")}>
          {task.title}
        </p>
      </div>

      <Badge tone={IMPORTANCE_TONE[task.importance]}>{task.importance}</Badge>

      {task.estimated_hours != null && (
        <span className="tnum shrink-0 text-[11px] text-ink-faint">
          {formatHours(task.estimated_hours)}
        </span>
      )}

      <span
        className={cn(
          "shrink-0 text-[11px] tnum",
          deadline.overdue ? "text-critical" : deadline.urgent ? "text-risk" : "text-ink-faint"
        )}
      >
        {deadline.label}
      </span>
    </div>
  );
}
