"use client";

import { FormEvent, KeyboardEvent, useRef, useState } from "react";
import { Plus } from "lucide-react";
import { TaskCreate } from "@/services/types";
import { cn } from "@/lib/format";

/**
 * The primary "add a task" interaction: a single-line input that creates
 * a task directly via POST /api/tasks, no AI parsing in the way. Enter
 * submits and keeps the input open for the next task (rapid entry, like
 * a to-do list), Escape closes it. The AI brain-dump agent is still
 * available — see IdeasPanel — but it's opt-in, not the default path.
 */
export function QuickAddTask({
  onAdd,
}: {
  onAdd: (payload: TaskCreate) => Promise<unknown>;
}) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function startAdding() {
    setOpen(true);
    requestAnimationFrame(() => inputRef.current?.focus());
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = title.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    try {
      await onAdd({ title: trimmed });
      setTitle("");
      // Stay open so the next task can be typed straight away.
      requestAnimationFrame(() => inputRef.current?.focus());
    } finally {
      setBusy(false);
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Escape") {
      setTitle("");
      setOpen(false);
    }
  }

  if (!open) {
    return (
      <button
        onClick={startAdding}
        className="flex w-full items-center gap-2 rounded-md border border-dashed border-hairline px-3 py-2.5 text-left text-[13px] text-ink-muted transition-colors hover:border-primary hover:text-ink"
      >
        <Plus size={15} />
        Add a task
      </button>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="flex items-center gap-2">
      <input
        ref={inputRef}
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        onKeyDown={handleKeyDown}
        onBlur={() => {
          if (!title.trim()) setOpen(false);
        }}
        placeholder="Finish CV assignment, gym tomorrow, interview Friday…"
        disabled={busy}
        className={cn(
          "w-full rounded-md border border-primary bg-surface-raised px-3 py-2.5 text-[13px] text-ink",
          "placeholder:text-ink-faint focus:outline-none"
        )}
      />
    </form>
  );
}
