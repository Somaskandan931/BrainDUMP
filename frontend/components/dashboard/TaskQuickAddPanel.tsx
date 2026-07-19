"use client";

import { Card, CardHeader } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { QuickAddTask } from "@/components/dashboard/QuickAddTask";
import { DraggableTaskList } from "@/components/dashboard/DraggableTaskList";
import { IdeasDisclosure } from "@/components/dashboard/IdeasDisclosure";
import { useTasks } from "@/hooks/useTasks";

export function TaskQuickAddPanel() {
  const { tasks, isLoading, create, complete, reorder, refresh } = useTasks({
    statusFilter: "pending",
  });

  return (
    <Card>
      <CardHeader eyebrow="Add them, drag to set priority" title="Your tasks" />

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
