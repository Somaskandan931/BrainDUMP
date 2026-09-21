"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useDeadlineRiskExplanation, useEstimateExplanation } from "@/hooks/useExplain";
import { ExplainError, ExplainLoading, ReasonList } from "@/components/explain/ReasonList";
import { TaskHistory } from "@/components/tasks/TaskHistory";
import { formatHours } from "@/lib/format";

function Disclosure({
  label,
  children,
}: {
  label: string;
  children: (open: boolean) => React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-md border border-hairline bg-surface-raised">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center gap-1.5 px-2.5 py-1.5 text-left text-[12px] font-medium text-ink-muted hover:text-ink"
      >
        {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        {label}
      </button>
      {open && <div className="border-t border-hairline px-3 py-2.5">{children(open)}</div>}
    </div>
  );
}

function EstimateBody({ taskId }: { taskId: number }) {
  const { explanation, isLoading, error } = useEstimateExplanation(taskId);
  if (isLoading) return <ExplainLoading label="Working out the estimate…" />;
  if (error || !explanation) return <ExplainError message="Couldn't load the estimate breakdown." />;

  const adjusted = Math.abs(explanation.calibration_applied_pct) > 1;
  return (
    <div className="flex flex-col gap-2.5">
      <p className="tnum text-[12px] text-ink">
        {formatHours(explanation.base_hours)} base
        {adjusted && (
          <>
            {" → "}
            <span className="font-medium">{formatHours(explanation.calibrated_hours)}</span> calibrated (
            {explanation.calibration_applied_pct > 0 ? "+" : ""}
            {explanation.calibration_applied_pct.toFixed(0)}%)
          </>
        )}
      </p>
      <ReasonList reasons={explanation.reasons} />
    </div>
  );
}

function RiskBody({ taskId }: { taskId: number }) {
  const { explanation, isLoading, error } = useDeadlineRiskExplanation(taskId);
  if (isLoading) return <ExplainLoading label="Checking the deadline…" />;
  if (error || !explanation) return <ExplainError message="Couldn't load the deadline breakdown." />;
  return <ReasonList reasons={explanation.reasons} />;
}

/**
 * The per-task "Why…?" panels, shown inside an expanded TaskRow. Each
 * panel is its own lazy disclosure, so opening a row costs nothing
 * until the user actually asks a question of it.
 */
export function TaskExplanations({
  taskId,
  hasDeadline,
  hasEstimate,
}: {
  taskId: number;
  hasDeadline: boolean;
  hasEstimate: boolean;
}) {
  return (
    <div className="flex flex-col gap-1.5 px-2 pb-3">
      {hasEstimate && (
        <Disclosure label="Why this estimate?">{() => <EstimateBody taskId={taskId} />}</Disclosure>
      )}
      {hasDeadline && (
        <Disclosure label="Why is this deadline at risk?">{() => <RiskBody taskId={taskId} />}</Disclosure>
      )}
      <Disclosure label="History">{() => <TaskHistory taskId={taskId} />}</Disclosure>
    </div>
  );
}
