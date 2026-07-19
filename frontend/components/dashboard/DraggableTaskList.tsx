"use client";

import { DragEvent, useState } from "react";
import { GripVertical } from "lucide-react";
import { Task } from "@/services/types";
import { TaskRow } from "@/components/tasks/TaskRow";
import { cn } from "@/lib/format";

/**
 * Plain HTML5 drag-and-drop — no extra library needed for a single
 * vertical list. Dropping calls onReorder with the new top-to-bottom id
 * order; the caller (useTasks().reorder) handles the optimistic update
 * and the POST /api/tasks/reorder call.
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
    <div className="flex flex-col gap-0.5">
      {tasks.map((task) => (
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
            "group/drag flex items-center gap-1 rounded-md transition-colors",
            overId === task.id && dragId !== task.id && "bg-primary-dim/40",
            dragId === task.id && "opacity-40"
          )}
        >
          <span className="cursor-grab pl-1 text-ink-faint opacity-0 transition-opacity group-hover/drag:opacity-100 active:cursor-grabbing">
            <GripVertical size={14} />
          </span>
          <div className="min-w-0 flex-1">
            <TaskRow task={task} onComplete={onComplete} />
          </div>
        </div>
      ))}
    </div>
  );
}
