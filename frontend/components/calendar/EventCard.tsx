import { format } from "date-fns";
import { CalendarDays, Sparkles, Pencil } from "lucide-react";
import { cn } from "@/lib/format";
import { CalendarEvent, EventSource } from "@/services/types";

const SOURCE_META: Record<
  EventSource,
  { label: string; icon: typeof CalendarDays; accent: string; dim: string; text: string }
> = {
  google: {
    label: "Google Calendar",
    icon: CalendarDays,
    accent: "bg-primary",
    dim: "bg-primary-dim",
    text: "text-primary-hover",
  },
  brain_dump: {
    label: "Work session",
    icon: Sparkles,
    accent: "bg-signal",
    dim: "bg-signal-dim",
    text: "text-signal",
  },
  manual: {
    label: "Manual",
    icon: Pencil,
    accent: "bg-risk",
    dim: "bg-risk-dim",
    text: "text-risk",
  },
};

function durationLabel(startIso: string, endIso: string): string {
  const ms = new Date(endIso).getTime() - new Date(startIso).getTime();
  const mins = Math.max(0, Math.round(ms / 60000));
  if (mins < 60) return `${mins}m`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return m === 0 ? `${h}h` : `${h}h ${m}m`;
}

/** One calendar event, rendered as a self-contained card. Meant to be
 * repeated in a grid — every card carries its own time, title, source,
 * and duration so it reads fine in isolation, not just in a list. */
export function EventCard({ event }: { event: CalendarEvent }) {
  const meta = SOURCE_META[event.source];
  const Icon = meta.icon;

  return (
    <div
      className={cn(
        "group relative flex flex-col gap-3 overflow-hidden rounded-panel border border-hairline",
        "bg-surface p-4 shadow-panel transition-colors hover:border-hairline hover:bg-surface-raised"
      )}
    >
      <span className={cn("absolute inset-y-0 left-0 w-[3px]", meta.accent)} aria-hidden="true" />

      <div className="flex items-start justify-between gap-3 pl-2">
        <div className="flex items-baseline gap-1.5 tnum">
          <span className="text-[15px] font-medium text-ink">
            {format(new Date(event.start_time), "h:mm a")}
          </span>
          <span className="text-[12px] text-ink-faint">
            – {format(new Date(event.end_time), "h:mm a")}
          </span>
        </div>
        <span className="shrink-0 text-[11px] tnum text-ink-faint">
          {durationLabel(event.start_time, event.end_time)}
        </span>
      </div>

      <p className="truncate pl-2 text-[14px] font-medium text-ink" title={event.title}>
        {event.title}
      </p>

      <div className="flex items-center gap-1.5 pl-2">
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium",
            meta.dim,
            meta.text
          )}
        >
          <Icon size={11} />
          {meta.label}
        </span>
        {event.sync_status === "not_synced" && (
          <span className="text-[10px] text-ink-faint">not synced</span>
        )}
      </div>
    </div>
  );
}
