"use client";

import { useMemo, useState } from "react";
import { format, isToday } from "date-fns";
import { CalendarDays, ListTodo, RefreshCw } from "lucide-react";
import { TopBar } from "@/components/layout/TopBar";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { useCalendarEvents } from "@/hooks/usePlanner";
import { calendarApi, todoistApi } from "@/services/api";
import { ApiError } from "@/services/types";
import { cn } from "@/lib/format";

const SOURCE_TONE = { google: "primary", brain_dump: "signal", manual: "neutral" } as const;

function SyncPanel() {
  const { refresh } = useCalendarEvents();
  const [calStatus, setCalStatus] = useState<string | null>(null);
  const [todoistStatus, setTodoistStatus] = useState<string | null>(null);
  const [syncingCal, setSyncingCal] = useState(false);
  const [syncingTodoist, setSyncingTodoist] = useState(false);

  async function syncCalendar() {
    setSyncingCal(true);
    setCalStatus(null);
    try {
      const res = await calendarApi.sync();
      setCalStatus(
        res.errors.length
          ? res.errors.join("; ")
          : `Pulled ${res.pulled}, pushed ${res.pushed}, removed ${res.removed}.`
      );
      await refresh();
    } catch (err) {
      setCalStatus(
        err instanceof ApiError && err.status === 424
          ? "Not configured — add credentials.json (see backend/integrations/INTEGRATIONS.md)."
          : err instanceof ApiError
            ? err.message
            : "Sync failed."
      );
    } finally {
      setSyncingCal(false);
    }
  }

  async function syncTodoist() {
    setSyncingTodoist(true);
    setTodoistStatus(null);
    try {
      const res = await todoistApi.sync();
      setTodoistStatus(
        res.errors.length
          ? res.errors.join("; ")
          : `Pulled ${res.pulled}, pushed ${res.pushed}, closed ${res.closed}.`
      );
    } catch (err) {
      setTodoistStatus(err instanceof ApiError ? err.message : "Sync failed.");
    } finally {
      setSyncingTodoist(false);
    }
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <Card>
        <CardHeader eyebrow="POST /api/calendar/sync" title="Google Calendar" />
        <p className="mb-3 text-[13px] text-ink-muted">
          Two-way pass: pulls remote events into the local cache, pushes scheduled work
          sessions out.
        </p>
        <Button variant="secondary" size="sm" onClick={syncCalendar} disabled={syncingCal}>
          <RefreshCw size={13} className={cn(syncingCal && "animate-spin")} />
          {syncingCal ? "Syncing…" : "Sync now"}
        </Button>
        {calStatus && <p className="mt-2 text-[12px] text-ink-faint">{calStatus}</p>}
      </Card>

      <Card>
        <CardHeader eyebrow="POST /api/todoist/sync" title="Todoist" />
        <p className="mb-3 text-[13px] text-ink-muted">
          Imports open Todoist items as tasks, pushes new Brain Dump tasks out, closes
          completed ones.
        </p>
        <Button variant="secondary" size="sm" onClick={syncTodoist} disabled={syncingTodoist}>
          <RefreshCw size={13} className={cn(syncingTodoist && "animate-spin")} />
          {syncingTodoist ? "Syncing…" : "Sync now"}
        </Button>
        {todoistStatus && <p className="mt-2 text-[12px] text-ink-faint">{todoistStatus}</p>}
      </Card>
    </div>
  );
}

export default function CalendarPage() {
  const { events, isLoading } = useCalendarEvents();

  const groups = useMemo(() => {
    const map = new Map<string, typeof events>();
    for (const ev of [...events].sort(
      (a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime()
    )) {
      const key = format(new Date(ev.start_time), "yyyy-MM-dd");
      map.set(key, [...(map.get(key) ?? []), ev]);
    }
    return Array.from(map.entries());
  }, [events]);

  return (
    <>
      <TopBar>
        <h1 className="font-display text-xl font-semibold text-ink">Calendar</h1>
        <p className="mt-0.5 text-[13px] text-ink-muted">
          Locally cached events from Google Calendar and Brain Dump work sessions.
        </p>
      </TopBar>

      <main className="flex-1 space-y-4 p-6 md:p-8">
        <SyncPanel />

        <Card>
          <CardHeader eyebrow="Live from /api/calendar/events" title="Upcoming" />
          {isLoading ? (
            <Skeleton className="h-40 w-full" />
          ) : groups.length === 0 ? (
            <EmptyState
              icon={<CalendarDays size={20} />}
              title="No cached events yet"
              description="Sync Google Calendar above, or let the scheduler pack tasks into work sessions."
            />
          ) : (
            <div className="flex flex-col gap-5">
              {groups.map(([day, dayEvents]) => (
                <div key={day}>
                  <div className="mb-2 flex items-center gap-2">
                    <ListTodo size={13} className="text-ink-faint" />
                    <span
                      className={cn(
                        "text-[12px] font-medium",
                        isToday(new Date(day)) ? "text-primary-hover" : "text-ink-muted"
                      )}
                    >
                      {format(new Date(day), "EEEE, MMM d")}
                    </span>
                  </div>
                  <div className="flex flex-col divide-y divide-hairline pl-5">
                    {dayEvents.map((ev) => (
                      <div key={ev.id} className="flex items-center justify-between gap-3 py-2">
                        <div className="min-w-0">
                          <p className="truncate text-[13px] text-ink">{ev.title}</p>
                          <p className="tnum text-[11px] text-ink-faint">
                            {format(new Date(ev.start_time), "h:mm a")} –{" "}
                            {format(new Date(ev.end_time), "h:mm a")}
                          </p>
                        </div>
                        <Badge tone={SOURCE_TONE[ev.source]}>{ev.source.replace("_", " ")}</Badge>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </main>
    </>
  );
}
