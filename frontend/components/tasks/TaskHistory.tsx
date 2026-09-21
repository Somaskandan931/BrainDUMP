"use client";

import { useTaskHistory } from "@/hooks/useExplain";
import { ExplainError, ExplainLoading } from "@/components/explain/ReasonList";
import { ActivityEntry } from "@/services/types";
import { timeAgo } from "@/lib/format";

// Maps activity_service action strings (see backend/services/workspace/
// activity_service.py call sites) to a short human label. Falls back to the
// raw action string for anything not listed here, so a new hook added later
// degrades gracefully instead of rendering nothing.
const ACTION_LABELS: Record<string, string> = {
  "task.created": "Created",
  "task.updated": "Updated",
  "task.completed": "Completed",
  "task.skipped": "Skipped",
  "task.archived": "Archived",
  "task.deadline_pushed": "Deadline pushed back",
  "schedule.replanned": "Rescheduled",
};

function actionLabel(entry: ActivityEntry): string {
  return ACTION_LABELS[entry.action] ?? entry.action;
}

// details is a free-form JSON blob (diffed old/new values, or a reason
// string for a deadline push) -- render it plainly rather than assuming a
// shape, since different actions populate it differently.
function detailSummary(entry: ActivityEntry): string | null {
  if (!entry.details || Object.keys(entry.details).length === 0) return null;
  const parts = Object.entries(entry.details).map(([key, value]) => {
    if (value && typeof value === "object" && "from" in value && "to" in value) {
      const { from, to } = value as { from: unknown; to: unknown };
      return `${key}: ${String(from)} → ${String(to)}`;
    }
    return `${key}: ${String(value)}`;
  });
  return parts.join(", ");
}

function ActorBadge({ actor }: { actor: string }) {
  // "user" actions are the common case and need no badge; "ai" and
  // "system" (nightly job, todoist sync) are the ones worth calling out.
  if (actor === "user") return null;
  return (
    <span className="rounded-sm bg-surface-raised px-1 py-px text-[10px] uppercase tracking-wide text-ink-faint">
      {actor}
    </span>
  );
}

export function TaskHistory({ taskId }: { taskId: number }) {
  const { entries, isLoading, error } = useTaskHistory(taskId);

  if (isLoading) return <ExplainLoading label="Loading history…" />;
  if (error) return <ExplainError message="Couldn't load this task's history." />;
  if (entries.length === 0) {
    return <p className="text-[12px] text-ink-faint">No activity recorded yet.</p>;
  }

  return (
    <ul className="flex flex-col gap-2">
      {entries.map((entry) => {
        const detail = detailSummary(entry);
        return (
          <li key={entry.id} className="flex flex-col gap-0.5 text-[12px]">
            <div className="flex items-center gap-1.5">
              <span className="font-medium text-ink">{actionLabel(entry)}</span>
              <ActorBadge actor={entry.actor} />
              <span className="tnum text-ink-faint">{timeAgo(entry.created_at)}</span>
            </div>
            {detail && <p className="text-ink-muted">{detail}</p>}
          </li>
        );
      })}
    </ul>
  );
}
