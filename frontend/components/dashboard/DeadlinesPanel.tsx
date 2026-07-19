"use client";

import { Clock } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { Badge } from "@/components/ui/Badge";
import { useTasks } from "@/hooks/useTasks";
import { formatDeadline } from "@/lib/format";

export function DeadlinesPanel() {
  const { tasks, isLoading } = useTasks({ statusFilter: "pending" });

  const withDeadlines = tasks
    .filter((t) => t.deadline)
    .sort((a, b) => new Date(a.deadline!).getTime() - new Date(b.deadline!).getTime());

  return (
    <Card>
      <CardHeader eyebrow="Calculated from your tasks" title="Your deadlines" />

      {isLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : withDeadlines.length === 0 ? (
        <div className="flex flex-col items-center gap-2 py-8 text-center">
          <Clock size={20} className="text-ink-faint" />
          <p className="text-[13px] text-ink-faint">
            Your deadlines appear here once you add a task.
          </p>
        </div>
      ) : (
        <ul className="flex flex-col gap-2.5">
          {withDeadlines.map((task) => {
            const deadline = formatDeadline(task.deadline);
            return (
              <li key={task.id} className="flex items-center justify-between gap-3">
                <span className="truncate text-[13px] text-ink">{task.title}</span>
                <Badge tone={deadline.overdue ? "critical" : deadline.urgent ? "risk" : "neutral"}>
                  {deadline.label}
                </Badge>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
