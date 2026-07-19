"use client";

import { AlertTriangle } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { Badge } from "@/components/ui/Badge";
import { useTasks } from "@/hooks/useTasks";
import { formatDeadline } from "@/lib/format";

export function DeadlineRiskCard() {
  const { tasks, isLoading } = useTasks();

  const atRisk = tasks
    .filter((t) => t.deadline && t.status !== "completed" && t.status !== "cancelled")
    .map((t) => ({ task: t, deadline: formatDeadline(t.deadline) }))
    .filter((x) => x.deadline.urgent || x.deadline.overdue)
    .sort((a, b) => new Date(a.task.deadline!).getTime() - new Date(b.task.deadline!).getTime())
    .slice(0, 6);

  return (
    <Card>
      <CardHeader eyebrow="Deadline service" title="Deadline risk" />
      {isLoading ? (
        <Skeleton className="h-28 w-full" />
      ) : atRisk.length === 0 ? (
        <EmptyState
          icon={<AlertTriangle size={20} />}
          title="Nothing at risk"
          description="Tasks within 2 days of their deadline, or overdue, show up here."
        />
      ) : (
        <ul className="flex flex-col gap-2.5">
          {atRisk.map(({ task, deadline }) => (
            <li key={task.id} className="flex items-center justify-between gap-3">
              <span className="truncate text-[13px] text-ink">{task.title}</span>
              <Badge tone={deadline.overdue ? "critical" : "risk"}>{deadline.label}</Badge>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
