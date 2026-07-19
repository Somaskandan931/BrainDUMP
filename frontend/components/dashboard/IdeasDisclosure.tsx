"use client";

import { useState } from "react";
import { ChevronDown, Sparkles } from "lucide-react";
import { BrainDumpForm } from "@/components/dashboard/BrainDumpForm";
import { cn } from "@/lib/format";

/**
 * The AI brain-dump agent, demoted from "the only way to add a task" to
 * an optional assist: paste a messy paragraph and let the parser split
 * it into projects/tasks, instead of typing one task at a time.
 */
export function IdeasDisclosure({ onDone }: { onDone?: () => void }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-md border border-hairline">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left text-[12px] font-medium uppercase tracking-wide text-primary-hover"
      >
        <span className="flex items-center gap-1.5">
          <Sparkles size={13} />
          Need ideas?
        </span>
        <ChevronDown size={14} className={cn("transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="border-t border-hairline p-3">
          <p className="mb-2 text-[11px] text-ink-faint">
            Paste a messy brain dump — the AI agent splits it into tasks and projects for you.
          </p>
          <BrainDumpForm compact onDone={onDone} />
        </div>
      )}
    </div>
  );
}
