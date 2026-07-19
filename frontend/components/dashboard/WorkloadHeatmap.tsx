"use client";

import { CalendarRange } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { Badge } from "@/components/ui/Badge";
import { useWorkload } from "@/hooks/usePlanner";
import { WorkloadDay, WorkloadLevel } from "@/services/types";
import { cn } from "@/lib/format";

const LEVEL_BAR_CLASS: Record<WorkloadLevel, string> = {
  light: "bg-signal",
  moderate: "bg-primary",
  full: "bg-risk",
  overloaded: "bg-critical",
};

const LEVEL_BADGE_TONE: Record<WorkloadLevel, "signal" | "primary" | "risk" | "critical"> = {
  light: "signal",
  moderate: "primary",
  full: "risk",
  overloaded: "critical",
};

/**
 * The Workload Engine (PRD Milestone 4 / Milestone 9's "workload
 * heatmap"): one bar per upcoming day, height ~ utilization against
 * working-hour capacity, so a glance answers "which day am I about to
 * overload" the way the PRD's ASCII mock (`Mon ██ Tue ████████ ...`)
 * sketched it — real numbers from services/workload_service.py.
 */
export function WorkloadHeatmap() {
  const { workload, isLoading } = useWorkload();

  return (
    <Card>
      <CardHeader
        eyebrow="Workload engine"
        title="This week's load"
        action={
          workload?.peak_day ? (
            <Badge tone="risk">Busiest: {workload.peak_day}</Badge>
          ) : undefined
        }
      />
      {isLoading ? (
        <Skeleton className="h-32 w-full" />
      ) : !workload || workload.days.length === 0 ? (
        <EmptyState
          icon={<CalendarRange size={20} />}
          title="Nothing scheduled yet"
          description="Once tasks are packed onto your calendar, daily load shows up here."
        />
      ) : (
        <>
          <div className="flex items-end justify-between gap-2 px-1">
            {workload.days.map((day) => (
              <DayBar key={day.date} day={day} />
            ))}
          </div>
          <div className="mt-4 flex items-center justify-between border-t border-hairline pt-3 text-[12px] text-ink-muted">
            <span>
              Week: <span className="tnum text-ink">{workload.week.allocated_hours}h</span> /{" "}
              <span className="tnum">{workload.week.capacity_hours}h</span>
            </span>
            <span className="tnum">{workload.week.utilization_pct}%</span>
          </div>
        </>
      )}
    </Card>
  );
}

function DayBar({ day }: { day: WorkloadDay }) {
  // Cap the visual fill at 100% so a wildly overbooked day still reads
  // as "full" rather than blowing out the layout; the badge/percentage
  // underneath carries the real (possibly >100%) number.
  const fillPct = Math.max(4, Math.min(100, day.utilization_pct));

  return (
    <div className="flex flex-1 flex-col items-center gap-1.5">
      <div className="flex h-20 w-full items-end rounded-md bg-surface-raised">
        <div
          className={cn("w-full rounded-md transition-all", LEVEL_BAR_CLASS[day.level])}
          style={{ height: `${fillPct}%` }}
          title={`${day.allocated_hours}h / ${day.capacity_hours}h`}
        />
      </div>
      <span className="text-[11px] font-medium text-ink-muted">{day.weekday}</span>
      <Badge tone={LEVEL_BADGE_TONE[day.level]}>{Math.round(day.utilization_pct)}%</Badge>
    </div>
  );
}
