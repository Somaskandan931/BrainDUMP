"use client";

import { AlertTriangle } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { Badge } from "@/components/ui/Badge";
import { useTasks } from "@/hooks/useTasks";
import { formatDeadline, formatPercent, friendlyApiError } from "@/lib/format";

/** Risk Score (deadline_service.py, PRD §19) is 0–1 — likelihood of
 * missing the deadline, not a date heuristic. Fall back to the local
 * "urgent/overdue" date check only for tasks the engine hasn't scored
 * yet (e.g. no deadline set at creation, so risk_score is still null). */
export function DeadlineRiskCard() {
  const { tasks, isLoading, error, refresh } = useTasks();

  const atRisk = tasks
    .filter((t) => t.deadline && t.status !== "completed" && t.status !== "cancelled")
    .map((t) => ({ task: t, deadline: formatDeadline(t.deadline) }))
    .filter((x) => (x.task.risk_score ?? 0) >= 0.5 || x.deadline.urgent || x.deadline.overdue)
    .sort((a, b) => (b.task.risk_score ?? 0) - (a.task.risk_score ?? 0))
    .slice(0, 6);

  return (
    <Card>
      <CardHeader eyebrow="Deadline Engine" title="Deadline risk" />
      {isLoading ? (
        <Skeleton className="h-28 w-full" />
      ) : error ? (
        <ErrorState
          message={friendlyApiError(error, "Couldn't load deadline risk.")}
          onRetry={() => refresh()}
        />
      ) : atRisk.length === 0 ? (
        <EmptyState
          icon={<AlertTriangle size={20} />}
          title="Nothing at risk"
          description="Tasks with a high risk score, or within 2 days of their deadline, show up here."
        />
      ) : (
        <ul className="flex flex-col gap-2.5">
          {atRisk.map(({ task, deadline }) => (
            <li key={task.id} className="flex items-center justify-between gap-3">
              <span className="truncate text-[13px] text-ink">{task.title}</span>
              <div className="flex shrink-0 items-center gap-1.5">
                {task.risk_score != null && (
                  <Badge tone={task.risk_score >= 0.7 ? "critical" : "risk"}>
                    {formatPercent(task.risk_score)} risk
                  </Badge>
                )}
                <Badge tone={deadline.overdue ? "critical" : "risk"}>{deadline.label}</Badge>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
