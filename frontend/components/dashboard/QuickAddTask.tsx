"use client";

import { FormEvent, KeyboardEvent, useRef, useState } from "react";
import { Plus } from "lucide-react";
import { TaskCreate } from "@/services/types";
import { cn } from "@/lib/format";

/**
 * The primary "add a task" interaction: title + a duration (hr/min)
 * picker, matching the Today dashboard mock — enter a title, adjust the
 * estimate if needed, hit Enter or "+ Add". Submitting keeps the panel
 * open with the fields reset so a rapid string of tasks can be typed
 * one after another (Escape/Cancel closes it). Duration feeds
 * estimated_hours, which the Deadline Engine and the schedule preview
 * on DeadlinesPanel both key off of.
 */
export function QuickAddTask({
  onAdd,
}: {
  onAdd: (payload: TaskCreate) => Promise<unknown>;
}) {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [hours, setHours] = useState(0);
  const [minutes, setMinutes] = useState(30);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  function startAdding() {
    setOpen(true);
    requestAnimationFrame(() => inputRef.current?.focus());
  }

  function reset() {
    setTitle("");
    setHours(0);
    setMinutes(30);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = title.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    try {
      const estimated = hours + minutes / 60;
      await onAdd({
        title: trimmed,
        estimated_hours: estimated > 0 ? estimated : undefined,
      });
      reset();
      // Stay open so the next task can be typed straight away.
      requestAnimationFrame(() => inputRef.current?.focus());
    } finally {
      setBusy(false);
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Escape") {
      reset();
      setOpen(false);
    }
  }

  function clampMinutes(n: number): number {
    if (Number.isNaN(n)) return 0;
    return Math.min(59, Math.max(0, n));
  }

  function clampHours(n: number): number {
    if (Number.isNaN(n)) return 0;
    return Math.min(23, Math.max(0, n));
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
    <form
      onSubmit={handleSubmit}
      className="flex flex-col gap-3 rounded-md border border-primary bg-surface-raised p-3"
    >
      <input
        ref={inputRef}
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="What do you need to do?"
        disabled={busy}
        className="w-full bg-transparent text-[13px] text-ink placeholder:text-ink-faint focus:outline-none"
      />

      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-1.5">
          <input
            type="number"
            min={0}
            max={23}
            value={hours}
            onChange={(e) => setHours(clampHours(e.target.valueAsNumber))}
            disabled={busy}
            className="tnum h-8 w-12 rounded-md border border-hairline bg-surface px-2 text-center text-[13px] text-ink focus:border-primary focus:outline-none"
          />
          <span className="text-[12px] text-ink-faint">hr</span>
          <input
            type="number"
            min={0}
            max={59}
            step={5}
            value={minutes}
            onChange={(e) => setMinutes(clampMinutes(e.target.valueAsNumber))}
            disabled={busy}
            className="tnum h-8 w-12 rounded-md border border-hairline bg-surface px-2 text-center text-[13px] text-ink focus:border-primary focus:outline-none"
          />
          <span className="text-[12px] text-ink-faint">min</span>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => {
              reset();
              setOpen(false);
            }}
            disabled={busy}
            className="h-8 rounded-md px-3 text-[13px] font-medium text-ink-muted transition-colors hover:text-ink"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={busy || !title.trim()}
            className={cn(
              "flex h-8 items-center gap-1 rounded-md bg-primary px-3 text-[13px] font-medium text-[#0A0B0F] transition-colors hover:bg-primary-hover",
              "disabled:cursor-not-allowed disabled:opacity-50"
            )}
          >
            <Plus size={14} />
            Add
          </button>
        </div>
      </div>
    </form>
  );
}
