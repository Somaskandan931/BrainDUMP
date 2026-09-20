"use client";

import { Card, CardHeader } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorState } from "@/components/ui/ErrorState";
import { QuickAddTask } from "@/components/dashboard/QuickAddTask";
import { DraggableTaskList } from "@/components/dashboard/DraggableTaskList";
import { IdeasDisclosure } from "@/components/dashboard/IdeasDisclosure";
import { useTasks } from "@/hooks/useTasks";
import { friendlyApiError } from "@/lib/format";

export function TaskQuickAddPanel() {
  const { tasks, isLoading, error, create, complete, reorder, refresh } = useTasks({
    statusFilter: "pending",
  });

  return (
    <Card>
      <CardHeader
        eyebrow="Add them, drag to set priority"
        title="Your tasks"
        action={
          !isLoading &&
          !error && (
            <span className="tnum whitespace-nowrap pt-0.5 text-[12px] text-ink-faint">
              {tasks.length} pending
            </span>
          )
        }
      />

      <div className="flex flex-col gap-2">
        <QuickAddTask onAdd={create} />
        <IdeasDisclosure onDone={refresh} />
      </div>

      <div className="mt-3">
        {isLoading ? (
          <div className="flex flex-col gap-2">
            <Skeleton className="h-9 w-full" />
            <Skeleton className="h-9 w-full" />
          </div>
        ) : error ? (
          <ErrorState
            message={friendlyApiError(error, "Couldn't load your tasks.")}
            onRetry={() => refresh()}
          />
        ) : tasks.length === 0 ? (
          <p className="py-6 text-center text-[13px] text-ink-faint">Add your first task above.</p>
        ) : (
          <DraggableTaskList
            tasks={tasks}
            onComplete={complete}
            onReorder={(ids) => reorder(ids)}
          />
        )}
      </div>
    </Card>
  );
}
