"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Play, Gauge, Check, Bell, ChevronDown, ChevronUp, ExternalLink } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/ErrorState";
import { Skeleton } from "@/components/ui/Skeleton";
import { useTasks } from "@/hooks/useTasks";
import { useWorkload, useDailyPlan } from "@/hooks/usePlanner";
import { BUFFER_MULTIPLIERS } from "@/services/types";
import { cn, formatHours, friendlyApiError, parseServerDate } from "@/lib/format";

// Where a task's buffer time comes from: duration * BASE_BUFFER_RATIO *
// the locked-in multiplier, so a 30m task at the "Default" (1x) stop
// gets an 8m buffer (30 * 0.25 * 1 ≈ 8, rounded), tightening toward 4m
// at 0.5x or loosening toward 13m at 1.75x. Mirrors
// schemas/schedule.BUFFER_MULTIPLIERS on the backend.
const DEFAULT_STEP_INDEX = BUFFER_MULTIPLIERS.indexOf(1);
const BASE_BUFFER_RATIO = 0.25;
const FALLBACK_AVAILABLE_HOURS = 8;

function todayKey(): string {
  return new Date().toISOString().slice(0, 10);
}

function bufferMinutesFor(durationHours: number, multiplier: number): number {
  const minutes = durationHours * 60 * BASE_BUFFER_RATIO * multiplier;
  return Math.max(1, Math.round(minutes));
}

function formatClock(d: Date): string {
  let h = d.getHours();
  const m = d.getMinutes();
  const suffix = h >= 12 ? "pm" : "am";
  h = h % 12;
  if (h === 0) h = 12;
  return `${h}:${String(m).padStart(2, "0")}${suffix}`;
}

// Same as formatClock but with seconds, for the live "current time" readout.
function formatClockPrecise(d: Date): string {
  let h = d.getHours();
  const m = d.getMinutes();
  const s = d.getSeconds();
  const suffix = h >= 12 ? "pm" : "am";
  h = h % 12;
  if (h === 0) h = 12;
  return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}${suffix}`;
}

// "in 12m 34s" while the deadline is ahead, "Overdue by 3m 10s" once it's
// passed. Used for the ticking countdown on the up-next task.
function formatCountdown(ms: number): string {
  const overdue = ms < 0;
  const totalSeconds = Math.floor(Math.abs(ms) / 1000);
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;
  const parts: string[] = [];
  if (h > 0) parts.push(`${h}h`);
  if (h > 0 || m > 0) parts.push(`${m}m`);
  if (h === 0) parts.push(`${s}s`);
  return `${overdue ? "Overdue by " : "in "}${parts.join(" ")}`;
}

// Fires a browser notification if the user has granted permission; a no-op
// otherwise (including SSR, where `Notification` doesn't exist).
function notify(title: string, body: string): void {
  if (typeof window === "undefined" || !("Notification" in window)) return;
  if (Notification.permission === "granted") {
    new Notification(title, { body });
  }
}

// "29:14" / "1:04:02" while ahead, "-03:10" once past due. Used for the
// compact hero countdown in the collapsed buffers view.
function formatCountdownClock(ms: number): string {
  const overdue = ms < 0;
  const totalSeconds = Math.floor(Math.abs(ms) / 1000);
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  const body = h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
  return overdue ? `-${body}` : body;
}

// Opens a small always-on-top-ish browser window with a self-contained
// ticking countdown to `due`, so the timer can sit off to the side of a
// desktop while the person works elsewhere. Desktop-only in practice —
// most mobile browsers ignore window.open's size hints or block popups.
function openPopout(title: string, due: Date): void {
  if (typeof window === "undefined") return;
  const popup = window.open("", "lunavigate-popout", "width=280,height=150,resizable=no");
  if (!popup) return;
  const dueMs = due.getTime();
  popup.document.write(`<!doctype html>
<html>
<head>
<title>${title}</title>
<style>
  body { margin:0; background:#0A0B0F; color:#F5F5F7; font-family: system-ui, sans-serif;
         display:flex; flex-direction:column; align-items:center; justify-content:center; height:100vh; }
  .clock { font-size: 42px; font-weight: 700; font-variant-numeric: tabular-nums; }
  .title { font-size: 13px; opacity:.7; margin-top: 8px; text-align:center; padding: 0 14px; }
</style>
</head>
<body>
<div class="clock" id="clock">--:--</div>
<div class="title"></div>
<script>
  document.querySelector(".title").textContent = ${JSON.stringify(title)};
  function fmt(ms) {
    var overdue = ms < 0;
    var total = Math.floor(Math.abs(ms) / 1000);
    var h = Math.floor(total / 3600);
    var m = Math.floor((total % 3600) / 60);
    var s = total % 60;
    var pad = function (n) { return String(n).padStart(2, "0"); };
    var body = h > 0 ? (h + ":" + pad(m) + ":" + pad(s)) : (pad(m) + ":" + pad(s));
    return overdue ? ("-" + body) : body;
  }
  function tick() {
    document.getElementById("clock").textContent = fmt(${dueMs} - Date.now());
  }
  tick();
  setInterval(tick, 1000);
</script>
</body>
</html>`);
  popup.document.close();
}

export function DeadlinesPanel() {
  const { tasks, isLoading, error, complete, skip, refresh } = useTasks({
    statusFilter: "pending",
  });
  const { workload } = useWorkload();
  const { plan, isLoading: planLoading, startDay } = useDailyPlan();

  // The slider is only ever a *pending* choice until "Start your day"
  // locks it in server-side; once locked, always defer to the server's
  // value (plan.buffer_multiplier) rather than local state, so a plan
  // started on another device/tab is reflected here too.
  const [pendingStepIndex, setPendingStepIndex] = useState(DEFAULT_STEP_INDEX);
  const [starting, setStarting] = useState(false);
  const [buffersExpanded, setBuffersExpanded] = useState(false);

  // Live clock: ticks every second so "current time" and the up-next
  // countdown actually move instead of only updating on the next SWR poll.
  // Starts as null (identical on server and first client render) and is
  // only populated after mount — seeding it with `new Date()` up front
  // causes a server/client text mismatch, since the server's timestamp is
  // always a beat behind the client's by the time hydration runs.
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  // Ask for notification permission once, so we can alert the user when the
  // up-next task's deadline hits (and 5 minutes before it does).
  useEffect(() => {
    if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "default") {
      Notification.requestPermission();
    }
  }, []);

  // Track which task ids we've already notified for, so a notification
  // fires once per task rather than once per second while overdue.
  const warnedRef = useRef<Set<number>>(new Set());
  const dueRef = useRef<Set<number>>(new Set());

  useEffect(() => {
    if (plan && !plan.locked) {
      const idx = BUFFER_MULTIPLIERS.indexOf(plan.buffer_multiplier as (typeof BUFFER_MULTIPLIERS)[number]);
      if (idx !== -1) setPendingStepIndex(idx);
    }
  }, [plan]);

  const locked = plan?.locked ?? false;
  const stepIndex = locked
    ? Math.max(0, BUFFER_MULTIPLIERS.indexOf(plan!.buffer_multiplier as (typeof BUFFER_MULTIPLIERS)[number]))
    : pendingStepIndex;
  const multiplier = BUFFER_MULTIPLIERS[stepIndex] ?? 1;
  const lockedAt = useMemo(
    () => (locked && plan?.started_at ? parseServerDate(plan.started_at) : null),
    [locked, plan?.started_at]
  );

  async function handleStartDay() {
    if (starting || locked || tasks.length === 0) return;
    setStarting(true);
    try {
      await startDay(multiplier);
    } finally {
      setStarting(false);
    }
  }

  const todayCapacity = useMemo(() => {
    const key = todayKey();
    const day = workload?.days.find((d) => d.date === key);
    return day?.capacity_hours ?? FALLBACK_AVAILABLE_HOURS;
  }, [workload]);

  const schedule = useMemo(() => {
    const anchor = lockedAt ?? new Date();
    let cursor = new Date(anchor);
    return tasks.map((task, index) => {
      const durationHours = task.estimated_hours ?? 0.5;
      const bufferMin = bufferMinutesFor(durationHours, multiplier);
      const start = new Date(cursor);
      const due = new Date(cursor.getTime() + durationHours * 60 * 60_000);
      cursor = new Date(due.getTime() + bufferMin * 60_000);
      return { task, start, due, bufferMin, isNext: index === 0 };
    });
  }, [tasks, lockedAt, multiplier]);

  useEffect(() => {
    const next = schedule[0];
    if (!next || !now) return;
    const taskId = next.task.id;
    const msLeft = next.due.getTime() - now.getTime();

    if (msLeft <= 0 && !dueRef.current.has(taskId)) {
      dueRef.current.add(taskId);
      notify(`${next.task.title} is due now`, "Mark it done or skip to move on to the next one.");
    } else if (msLeft > 0 && msLeft <= 5 * 60_000 && !warnedRef.current.has(taskId)) {
      warnedRef.current.add(taskId);
      notify(`${next.task.title} due in 5 minutes`, `Due by ${formatClock(next.due)}`);
    }
  }, [schedule, now]);

  // Drives the collapsed buffers hero: countdown to the up-next task's
  // due time, plus a qualitative read on how much slack is left.
  const nextItem = schedule[0] ?? null;
  const heroMsLeft = nextItem && now ? nextItem.due.getTime() - now.getTime() : null;
  const heroClock = heroMsLeft === null ? "--:--" : formatCountdownClock(heroMsLeft);
  const heroMessage = (() => {
    if (!nextItem || heroMsLeft === null) return "Nothing scheduled";
    if (heroMsLeft <= 0) return "overdue — mark it done or skip";
    const totalMs = nextItem.due.getTime() - nextItem.start.getTime();
    const ratio = totalMs > 0 ? heroMsLeft / totalMs : 0;
    if (ratio > 0.5) return "plenty of time — ease in";
    if (ratio > 0.2) return "on track";
    return "getting tight";
  })();

  const plannedHours = useMemo(() => {
    const totalMinutes = schedule.reduce((sum, s) => {
      const durationMin = (s.task.estimated_hours ?? 0.5) * 60;
      return sum + durationMin + s.bufferMin;
    }, 0);
    return totalMinutes / 60;
  }, [schedule]);

  const fullPct = todayCapacity > 0 ? Math.min(100, Math.round((plannedHours / todayCapacity) * 100)) : 0;

  return (
    <Card>
      <CardHeader
        eyebrow="Calculated from your tasks"
        title="Your deadlines"
        action={
          <span className="tnum flex items-center gap-1 text-[11px] text-ink-faint">
            <Bell size={11} />
            {now ? formatClockPrecise(now) : "--:--:--"}
          </span>
        }
      />

      {isLoading || planLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : error ? (
        <ErrorState
          message={friendlyApiError(error, "Couldn't load your deadlines.")}
          onRetry={() => refresh()}
        />
      ) : (
        <>
          <div className="rounded-md border border-hairline bg-surface-raised p-3">
            <button
              type="button"
              onClick={() => setBuffersExpanded((v) => !v)}
              className="flex w-full items-center justify-between text-left"
            >
              <span className="flex items-center gap-1.5 text-[12px] font-medium text-ink-muted">
                <Gauge size={13} />
                Buffers
                <span className="text-ink-faint">
                  {stepIndex === DEFAULT_STEP_INDEX ? "Default" : `${multiplier}x`}
                </span>
              </span>
              {buffersExpanded ? (
                <ChevronUp size={14} className="text-ink-faint" />
              ) : (
                <ChevronDown size={14} className="text-ink-faint" />
              )}
            </button>

            {buffersExpanded ? (
              <div className="mt-2">
                <input
                  type="range"
                  min={0}
                  max={BUFFER_MULTIPLIERS.length - 1}
                  step={1}
                  value={stepIndex}
                  disabled={locked}
                  onChange={(e) => setPendingStepIndex(Number(e.target.value))}
                  className={cn("w-full accent-primary", locked && "cursor-not-allowed opacity-50")}
                />
                <div className="mt-1 flex justify-between text-[11px] text-ink-faint">
                  <span>Tight</span>
                  <span>Default</span>
                  <span>Relaxed</span>
                </div>
              </div>
            ) : (
              nextItem && (
                <div className="mt-2 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-baseline gap-2">
                      <span className="tnum text-[26px] font-semibold text-primary">{heroClock}</span>
                      <span className="truncate text-[12px] text-ink-faint">{heroMessage}</span>
                    </div>
                    <div className="mt-0.5 truncate text-[12px] text-ink-muted">
                      {nextItem.task.title} · due {formatClock(nextItem.due)}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => openPopout(nextItem.task.title, nextItem.due)}
                    className="flex shrink-0 flex-col items-center gap-1 rounded-md border border-hairline px-2.5 py-1.5 text-[11px] text-ink-muted transition-colors hover:text-ink"
                  >
                    <span className="flex items-center gap-1">
                      <ExternalLink size={12} />
                      Pop out
                    </span>
                    <span className="rounded bg-surface-overlay px-1 text-[9px] uppercase tracking-wide text-ink-faint">
                      PC only
                    </span>
                  </button>
                </div>
              )
            )}

            <div className="mt-3 flex items-center justify-between text-[12px]">
              <span className="text-ink-muted">
                <span className="tnum text-ink">{formatHours(plannedHours)}</span> planned of{" "}
                <span className="tnum text-ink">{formatHours(todayCapacity)}</span> available
              </span>
              <span
                className={cn(
                  "tnum font-medium",
                  fullPct >= 90 ? "text-critical" : fullPct >= 70 ? "text-risk" : "text-signal"
                )}
              >
                {fullPct}% full
              </span>
            </div>
            <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-surface-overlay">
              <div
                className={cn(
                  "h-full rounded-full transition-all",
                  fullPct >= 90 ? "bg-critical" : fullPct >= 70 ? "bg-risk" : "bg-signal"
                )}
                style={{ width: `${fullPct}%` }}
              />
            </div>
          </div>

          <button
            onClick={handleStartDay}
            disabled={locked || starting || tasks.length === 0}
            className={cn(
              "mt-3 flex w-full flex-col items-center gap-0.5 rounded-md py-3 text-center transition-colors",
              locked
                ? "cursor-default bg-signal-dim text-signal"
                : "bg-primary text-[#0A0B0F] hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-50"
            )}
          >
            <span className="flex items-center gap-1.5 text-[14px] font-semibold">
              {locked ? (
                <>
                  <Check size={15} />
                  Day started
                </>
              ) : (
                <>
                  <Play size={13} fill="currentColor" />
                  {starting ? "Starting…" : "Start your day"}
                </>
              )}
            </span>
            <span className="text-[11px] opacity-80">
              {locked ? "Deadlines and buffers are locked in" : "Lock in your deadlines"}
            </span>
          </button>

          <div className="mt-4">
            {schedule.length === 0 ? (
              <p className="py-6 text-center text-[13px] text-ink-faint">
                Your deadlines appear here once you add a task.
              </p>
            ) : (
              schedule.map((item, i) => (
                <div key={item.task.id}>
                  <div className="rounded-md border border-hairline bg-surface-raised p-3">
                    <div className="mb-1 flex items-center justify-between">
                      <span
                        className={cn(
                          "text-[10px] font-semibold uppercase tracking-wide",
                          item.isNext ? "text-primary-hover" : "text-ink-faint"
                        )}
                      >
                        {item.isNext ? "Up next" : `Due by ${formatClock(item.due)}`}
                      </span>
                      {item.isNext && (
                        <span className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide">
                          {now && (
                            <span
                              className={cn(
                                "tnum",
                                item.due.getTime() - now.getTime() <= 0
                                  ? "text-critical"
                                  : item.due.getTime() - now.getTime() <= 5 * 60_000
                                  ? "text-risk"
                                  : "text-ink-faint"
                              )}
                            >
                              {formatCountdown(item.due.getTime() - now.getTime())}
                            </span>
                          )}
                          <span className="text-ink-faint">Due by {formatClock(item.due)}</span>
                        </span>
                      )}
                    </div>

                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate text-[13px] font-medium text-ink">
                        {item.task.title}
                      </span>
                      <span className="tnum shrink-0 text-[11px] text-ink-faint">
                        {formatHours(item.task.estimated_hours ?? 0.5)}
                      </span>
                    </div>

                    <div className="mt-2 flex items-center gap-4 text-[12px] font-medium">
                      <button
                        onClick={() => skip(item.task.id)}
                        className="text-ink-faint transition-colors hover:text-ink-muted"
                      >
                        Skip
                      </button>
                      <button
                        onClick={() => complete(item.task.id)}
                        className="text-signal transition-colors hover:text-signal/80"
                      >
                        Done
                      </button>
                    </div>
                  </div>

                  {i < schedule.length - 1 && (
                    <div className="py-1.5 text-center text-[11px] text-ink-faint">
                      {item.bufferMin}m buffer
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </>
      )}
    </Card>
  );
}