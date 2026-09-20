"use client";

import { useMemo, useState } from "react";
import { format, isToday } from "date-fns";
import { CalendarDays, RefreshCw } from "lucide-react";
import { TopBar } from "@/components/layout/TopBar";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { EventCard } from "@/components/calendar/EventCard";
import { useCalendarEvents } from "@/hooks/usePlanner";
import { calendarApi } from "@/services/api";
import { ApiError } from "@/services/types";
import { friendlyApiError, cn } from "@/lib/format";

function SyncPanel({ onSynced }: { onSynced: () => void }) {
  const [calStatus, setCalStatus] = useState<string | null>(null);
  const [calStatusIsError, setCalStatusIsError] = useState(false);
  const [syncingCal, setSyncingCal] = useState(false);

  async function syncCalendar() {
    setSyncingCal(true);
    setCalStatus(null);
    setCalStatusIsError(false);
    try {
      const res = await calendarApi.sync();
      setCalStatusIsError(res.errors.length > 0);
      setCalStatus(
        res.errors.length
          ? res.errors.join("; ")
          : `Pulled ${res.pulled}, pushed ${res.pushed}, removed ${res.removed}.`
      );
      onSynced();
    } catch (err) {
      setCalStatusIsError(true);
      setCalStatus(
        err instanceof ApiError && err.status === 424
          ? "Not configured — add credentials.json to the ai_os/ root (see backend/integrations/INTEGRATIONS.md)."
          : err instanceof ApiError
            ? err.message
            : "Sync failed."
      );
    } finally {
      setSyncingCal(false);
    }
  }

  return (
    <Card className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <CardHeader eyebrow="POST /api/calendar/sync" title="Google Calendar" />
        <p className="-mt-3 text-[13px] text-ink-muted">
          Two-way pass: pulls remote events into the local cache, pushes scheduled work
          sessions out.
        </p>
        {calStatus && (
          <p className={cn("mt-2 text-[12px]", calStatusIsError ? "text-critical" : "text-ink-faint")}>
            {calStatus}
          </p>
        )}
      </div>
      <Button variant="secondary" size="sm" onClick={syncCalendar} disabled={syncingCal} className="shrink-0">
        <RefreshCw size={13} className={cn(syncingCal && "animate-spin")} />
        {syncingCal ? "Syncing…" : "Sync now"}
      </Button>
    </Card>
  );
}

export default function CalendarPage() {
  const { events, isLoading, error, refresh } = useCalendarEvents();

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

      <main className="flex-1 space-y-6 p-6 md:p-8">
        <SyncPanel onSynced={() => refresh()} />

        {isLoading ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-[104px] w-full" />
            ))}
          </div>
        ) : error ? (
          <ErrorState
            message={friendlyApiError(error, "Couldn't load calendar events.")}
            onRetry={() => refresh()}
          />
        ) : groups.length === 0 ? (
          <EmptyState
            icon={<CalendarDays size={20} />}
            title="No cached events yet"
            description="Sync Google Calendar above, or let the scheduler pack tasks into work sessions."
          />
        ) : (
          <div className="space-y-8">
            {groups.map(([day, dayEvents]) => (
              <section key={day}>
                <div className="mb-3 flex items-baseline gap-2">
                  <h2
                    className={cn(
                      "font-display text-[14px] font-medium",
                      isToday(new Date(day)) ? "text-primary-hover" : "text-ink"
                    )}
                  >
                    {format(new Date(day), "EEEE, MMM d")}
                  </h2>
                  <span className="text-[11px] tnum text-ink-faint">
                    {dayEvents.length} event{dayEvents.length === 1 ? "" : "s"}
                  </span>
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
                  {dayEvents.map((ev) => (
                    <EventCard key={ev.id} event={ev} />
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </main>
    </>
  );
}
