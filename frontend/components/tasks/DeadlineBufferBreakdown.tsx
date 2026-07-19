"use client";

import { Loader2 } from "lucide-react";
import { useDeadlinePlan } from "@/hooks/useTasks";
import { Badge } from "@/components/ui/Badge";
import { BufferStatus } from "@/services/types";
import { cn } from "@/lib/format";

const STATUS_TONE: Record<BufferStatus, "signal" | "risk" | "critical" | "neutral"> = {
  safe: "signal",
  tight: "risk",
  impossible: "critical",
  done: "neutral",
};

const STATUS_LABEL: Record<BufferStatus, string> = {
  safe: "Comfortable",
  tight: "Tight",
  impossible: "Won't fit",
  done: "Done",
};

const LEVEL_LABEL = {
  aggressive: "Aggressive",
  default: "Default",
  safe: "Safe",
} as const;

/**
 * The Deadline Engine's buffer breakdown for one task — fetched lazily
 * (only while `taskId` is non-null, i.e. the row is expanded), so
 * collapsed rows never pay for a request.
 */
export function DeadlineBufferBreakdown({ taskId }: { taskId: number }) {
  const { plan, isLoading, error } = useDeadlinePlan(taskId);

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 px-2 py-3 text-[12px] text-ink-faint">
        <Loader2 size={13} className="animate-spin" />
        Working out the buffer plan…
      </div>
    );
  }

  if (error || !plan) {
    return (
      <p className="px-2 py-3 text-[12px] text-ink-faint">
        Couldn&apos;t load the deadline plan for this task.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-1.5 px-2 pb-3 pt-1">
      <p className="px-1 text-[11px] text-ink-faint">
        {plan.hours_remaining > 0
          ? `${plan.hours_remaining}h of work left`
          : "No estimated work left"}
      </p>
      {plan.buffers.map((buffer) => (
        <div
          key={buffer.level}
          className="flex items-center gap-2.5 rounded-md border border-hairline bg-surface-raised px-2.5 py-2"
        >
          <span className="w-[70px] shrink-0 text-[11px] font-medium text-ink-muted">
            {LEVEL_LABEL[buffer.level]}
          </span>
          <div className="min-w-0 flex-1">
            <p className={cn("truncate text-[12px] text-ink")}>{buffer.message}</p>
          </div>
          <Badge tone={STATUS_TONE[buffer.status]}>{STATUS_LABEL[buffer.status]}</Badge>
        </div>
      ))}
    </div>
  );
}
