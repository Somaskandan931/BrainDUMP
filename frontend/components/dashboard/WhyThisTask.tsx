"use client";

import { useNextTaskExplanation } from "@/hooks/useExplain";
import { PriorityBreakdown } from "@/components/explain/PriorityBreakdown";
import { ExplainError, ExplainLoading, ReasonList } from "@/components/explain/ReasonList";

/** "Why this task?" — expands under the Do-next card. Only mounted (and
 * therefore only fetching) while the card's toggle is open. */
export function WhyThisTask({ taskId }: { taskId: number }) {
  const { explanation, isLoading, error } = useNextTaskExplanation(taskId);

  if (isLoading) return <ExplainLoading label="Working out why…" />;
  if (error || !explanation) {
    return <ExplainError message="Couldn't load the explanation for this recommendation." />;
  }

  return (
    <div className="flex flex-col gap-3 rounded-md border border-hairline bg-surface-raised px-3.5 py-3">
      <p className="text-[12px] font-medium text-ink">
        Picked because
      </p>
      <ReasonList reasons={explanation.reasons} />
      <div className="border-t border-hairline pt-3">
        <p className="mb-2 text-[11px] uppercase tracking-[0.12em] text-ink-faint">Priority inputs</p>
        <PriorityBreakdown components={explanation.components} />
      </div>
    </div>
  );
}
