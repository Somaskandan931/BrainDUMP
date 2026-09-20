"use client";

import { DragEvent, useState } from "react";
import { Clock, GripVertical } from "lucide-react";
import { Task } from "@/services/types";
import { formatHours, cn } from "@/lib/format";

/**
 * Plain HTML5 drag-and-drop — no extra library needed for a single
 * vertical list. Dropping calls onReorder with the new top-to-bottom id
 * order; the caller (useTasks().reorder) handles the optimistic update
 * and the POST /api/tasks/reorder call.
 *
 * The HIGH/LOW rail on the left is purely a visual read of list
 * position — top of the list is the highest priority task, bottom is
 * lowest — so dragging a task up *is* raising its priority, with no
 * separate "importance" field to keep in sync.
 */
export function DraggableTaskList({
  tasks,
  onComplete,
  onReorder,
}: {
  tasks: Task[];
  onComplete?: (id: number) => void;
  onReorder: (orderedIds: number[]) => void;
}) {
  const [dragId, setDragId] = useState<number | null>(null);
  const [overId, setOverId] = useState<number | null>(null);

  function handleDrop() {
    if (dragId == null || overId == null || dragId === overId) {
      setDragId(null);
      setOverId(null);
      return;
    }
    const ids = tasks.map((t) => t.id);
    const from = ids.indexOf(dragId);
    const to = ids.indexOf(overId);
    const [moved] = ids.splice(from, 1);
    if (moved == null) return;
    ids.splice(to, 0, moved);
    onReorder(ids);
    setDragId(null);
    setOverId(null);
  }

  return (
    <div className="flex items-stretch gap-2.5">
      {tasks.length > 1 && (
        <div className="flex w-8 shrink-0 flex-col items-center py-1 text-[10px] font-semibold uppercase tracking-wide text-ink-faint">
          <span>High</span>
          <div className="my-1 w-px flex-1 bg-gradient-to-b from-critical/50 via-hairline to-primary/40" />
          <span>Low</span>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
        {tasks.map((task, index) => (
          <div
            key={task.id}
            draggable
            onDragStart={() => setDragId(task.id)}
            onDragOver={(e: DragEvent) => {
              e.preventDefault();
              if (task.id !== overId) setOverId(task.id);
            }}
            onDrop={handleDrop}
            onDragEnd={() => {
              setDragId(null);
              setOverId(null);
            }}
            className={cn(
              "group/drag flex items-center gap-1 rounded-md border border-hairline bg-surface-raised px-1 transition-colors",
              overId === task.id && dragId !== task.id && "border-primary/60 bg-primary-dim/40",
              dragId === task.id && "opacity-40"
            )}
          >
            <span className="cursor-grab pl-1.5 text-ink-faint opacity-0 transition-opacity group-hover/drag:opacity-100 active:cursor-grabbing">
              <GripVertical size={14} />
            </span>

            <button
              onClick={() => onComplete?.(task.id)}
              disabled={!onComplete}
              aria-label={`Mark "${task.title}" complete`}
              className="min-w-0 flex-1 py-2.5 text-left"
            >
              <span
                className={cn(
                  "block truncate text-[13px]",
                  index === 0 ? "font-semibold text-ink" : "text-ink-muted"
                )}
              >
                {task.title}
              </span>
            </button>

            <span className="tnum flex shrink-0 items-center gap-1 pr-3 text-[11px] text-ink-faint">
              <Clock size={11} />
              {formatHours(task.estimated_hours ?? 0.5)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
