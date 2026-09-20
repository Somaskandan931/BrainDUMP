"use client";

import { useState } from "react";
import { Check, ChevronDown, ChevronRight } from "lucide-react";
import { Task } from "@/services/types";
import { Badge } from "@/components/ui/Badge";
import { DeadlineBufferBreakdown } from "@/components/tasks/DeadlineBufferBreakdown";
import { TaskExplanations } from "@/components/tasks/TaskExplanations";
import { cn, formatDeadline, formatHours, formatPercent } from "@/lib/format";

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
  const [expanded, setExpanded] = useState(false);
  // The deadline-plan and explain-deadline-risk endpoints 400 for tasks with no
  // deadline (useTasks.ts useDeadlinePlan comment), so those sections only render
  // when there is one; a task with just an estimate can still explain that.
  // Dense rows (dashboard cards) stay compact; the full breakdown lives on the
  // project page where there's room for it.
  const hasDeadline = !!task.deadline;
  const hasEstimate = task.estimated_hours != null;
  const expandable = !dense && (hasDeadline || hasEstimate) && !done;
  const highRisk = task.risk_score != null && task.risk_score >= 0.5;

  return (
    <div className={cn(dense ? "" : "rounded-md hover:bg-surface-raised")}>
      <div
        className={cn(
          "group flex items-center gap-3 rounded-md border border-transparent px-2 py-2 hover:border-hairline",
          dense && "py-1.5"
        )}
      >
        {expandable ? (
          <button
            onClick={() => setExpanded((e) => !e)}
            aria-label={expanded ? "Collapse task details" : "Show task details"}
            className="flex h-5 w-5 shrink-0 items-center justify-center text-ink-faint hover:text-ink"
          >
            {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          </button>
        ) : (
          !dense && <span className="w-5 shrink-0" />
        )}

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

        {highRisk && (
          <Badge tone={task.risk_score! >= 0.7 ? "critical" : "risk"}>
            {formatPercent(task.risk_score)} risk
          </Badge>
        )}

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

      {expandable && expanded && (
        <div className="pl-10">
          {hasDeadline && task.completion_probability != null && (
            <p className="px-1 pb-1 text-[11px] text-ink-faint">
              {formatPercent(task.completion_probability)} completion probability
            </p>
          )}
          {hasDeadline && <DeadlineBufferBreakdown taskId={task.id} />}
          <TaskExplanations taskId={task.id} hasDeadline={hasDeadline} hasEstimate={hasEstimate} />
        </div>
      )}
    </div>
  );
}
