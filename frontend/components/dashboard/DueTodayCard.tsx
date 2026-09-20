"use client";

import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { RadialGauge } from "./RadialGauge";
import { TaskRow } from "@/components/tasks/TaskRow";
import { useTasks } from "@/hooks/useTasks";
import { Task } from "@/services/types";
import { friendlyApiError } from "@/lib/format";
import { CalendarCheck } from "lucide-react";

function isToday(iso: string | null): boolean {
  if (!iso) return false;
  const d = new Date(iso);
  const now = new Date();
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  );
}

export function DueTodayCard() {
  const { tasks, isLoading, error, complete, refresh } = useTasks();

  const dueToday = tasks.filter(
    (t: Task) => isToday(t.deadline) || (t.status === "in_progress" && !t.deadline)
  );
  const completedToday = dueToday.filter((t) => t.status === "completed").length;
  const progress = dueToday.length === 0 ? 0 : (completedToday / dueToday.length) * 100;

  return (
    <Card>
      <CardHeader eyebrow="Task tracker" title="Due today" />
      {isLoading ? (
        <Skeleton className="h-32 w-full" />
      ) : error ? (
        <ErrorState
          message={friendlyApiError(error, "Couldn't load today's tasks.")}
          onRetry={() => refresh()}
        />
      ) : dueToday.length === 0 ? (
        <EmptyState
          icon={<CalendarCheck size={22} />}
          title="Nothing due today"
          description="Tasks with today's deadline, or already in progress, show up here."
        />
      ) : (
        <div className="flex items-start gap-5">
          <RadialGauge
            value={progress}
            sublabel={`${completedToday}/${dueToday.length} done`}
            tone="signal"
          />
          <div className="flex-1 divide-y divide-hairline">
            {dueToday.map((t) => (
              <TaskRow key={t.id} task={t} onComplete={(id) => complete(id)} dense />
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}
