"use client";

import useSWR from "swr";
import { Flame, LineChart, Sparkles, TrendingDown, TrendingUp } from "lucide-react";
import { ReactNode } from "react";
import { TopBar } from "@/components/layout/TopBar";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { Badge } from "@/components/ui/Badge";
import { WorkloadHeatmap } from "@/components/dashboard/WorkloadHeatmap";
import { analyticsApi } from "@/services/api";
import { ApiError, EstimationBias } from "@/services/types";

function PanelShell({
  eyebrow,
  title,
  isLoading,
  error,
  empty,
  emptyDescription,
  children,
}: {
  eyebrow: string;
  title: string;
  isLoading: boolean;
  error: unknown;
  empty: boolean;
  emptyDescription: string;
  children: ReactNode;
}) {
  return (
    <Card>
      <CardHeader eyebrow={eyebrow} title={title} />
      {isLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : error ? (
        <p className="text-[13px] text-critical">
          {error instanceof ApiError ? error.message : "Couldn't load this panel."}
        </p>
      ) : empty ? (
        <EmptyState icon={<LineChart size={18} />} title="Not enough history yet" description={emptyDescription} />
      ) : (
        children
      )}
    </Card>
  );
}

function WeeklyReviewPanel() {
  const { data, error, isLoading } = useSWR("weekly-review", analyticsApi.weeklyReview, {
    shouldRetryOnError: false,
  });

  return (
    <PanelShell
      eyebrow="GET /api/analytics/weekly-review"
      title="Weekly review"
      isLoading={isLoading}
      error={error}
      empty={!!data && data.tasks_planned === 0 && data.tasks_completed === 0}
      emptyDescription="Once a week of task activity is logged, your review shows up here."
    >
      {data && (
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3 text-[13px]">
            <Stat label="Completed" value={`${data.tasks_completed} / ${data.tasks_planned}`} />
            <Stat
              label="Completion rate"
              value={data.completion_rate != null ? `${Math.round(data.completion_rate * 100)}%` : "—"}
            />
            <Stat label="Hours worked" value={`${data.hours_worked}h`} />
            <Stat
              label="Missed deadlines"
              value={String(data.missed_deadlines)}
              tone={data.missed_deadlines > 0 ? "critical" : undefined}
            />
          </div>

          {(data.most_productive_day || data.least_productive_day) && (
            <p className="text-[12px] text-ink-muted">
              Best day: <span className="text-ink">{data.most_productive_day ?? "—"}</span> · Slowest:{" "}
              <span className="text-ink">{data.least_productive_day ?? "—"}</span>
            </p>
          )}

          {data.project_progress.length > 0 && (
            <div className="flex flex-col gap-1.5 border-t border-hairline pt-3">
              {data.project_progress.map((p) => (
                <div key={p.project_id} className="flex items-center justify-between gap-3 text-[12px]">
                  <span className="truncate text-ink-muted">{p.project_name}</span>
                  <span className="tnum text-ink">
                    {p.tasks_completed}/{p.tasks_total}
                  </span>
                </div>
              ))}
            </div>
          )}

          <div className="flex items-start gap-2 rounded-md border border-hairline bg-surface-raised px-3 py-2.5">
            <Sparkles size={14} className="mt-0.5 shrink-0 text-primary-hover" />
            <p className="text-[12px] text-ink-muted">
              {data.recommendation}
              {!data.ai_generated && <span className="ml-1 text-ink-faint">(rule-based — Ollama offline)</span>}
            </p>
          </div>
        </div>
      )}
    </PanelShell>
  );
}

function EstimationErrorPanel() {
  const { data, error, isLoading } = useSWR("estimation-error", analyticsApi.estimationError, {
    shouldRetryOnError: false,
  });

  const BIAS_LABEL: Record<EstimationBias, string> = {
    overestimates: "Overestimates",
    underestimates: "Underestimates",
    accurate: "Accurate",
  };
  const BIAS_TONE: Record<EstimationBias, "signal" | "risk" | "neutral"> = {
    overestimates: "risk",
    underestimates: "risk",
    accurate: "signal",
  };

  return (
    <PanelShell
      eyebrow="GET /api/analytics/estimation-error"
      title="Estimation accuracy"
      isLoading={isLoading}
      error={error}
      empty={!!data && data.overall_sample_count === 0}
      emptyDescription="Complete a few tasks with logged hours and your estimation bias shows up here."
    >
      {data && (
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2">
            {data.overall_average_error_pct != null && data.overall_average_error_pct > 0 ? (
              <TrendingDown size={16} className="text-risk" />
            ) : (
              <TrendingUp size={16} className="text-signal" />
            )}
            <p className="text-[13px] text-ink">
              Overall bias:{" "}
              <span className="tnum font-medium">
                {data.overall_average_error_pct != null ? `${data.overall_average_error_pct}%` : "—"}
              </span>{" "}
              across {data.overall_sample_count} task{data.overall_sample_count === 1 ? "" : "s"}
            </p>
          </div>
          <div className="flex flex-col gap-1.5">
            {data.by_category.map((c) => (
              <div
                key={c.category}
                className="flex items-center justify-between gap-3 rounded-md border border-hairline bg-surface-raised px-2.5 py-2"
              >
                <span className="truncate text-[12px] text-ink">{c.category}</span>
                <div className="flex items-center gap-2">
                  <span className="tnum text-[11px] text-ink-faint">
                    {c.sample_count} sample{c.sample_count === 1 ? "" : "s"}
                  </span>
                  <Badge tone={BIAS_TONE[c.bias]}>{BIAS_LABEL[c.bias]}</Badge>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </PanelShell>
  );
}

function StreaksPanel() {
  const { data, error, isLoading } = useSWR("streaks", analyticsApi.streaks, {
    shouldRetryOnError: false,
  });

  return (
    <PanelShell
      eyebrow="GET /api/analytics/streaks"
      title="Streaks"
      isLoading={isLoading}
      error={error}
      empty={!!data && data.longest_streak_days === 0}
      emptyDescription="Log a day of work and your streak starts counting here."
    >
      {data && (
        <div className="flex items-center gap-6">
          <div className="flex flex-col items-center gap-1">
            <div className="flex items-center gap-1.5">
              <Flame size={18} className={data.active_today ? "text-risk" : "text-ink-faint"} />
              <span className="tnum font-display text-2xl font-semibold text-ink">
                {data.current_streak_days}
              </span>
            </div>
            <span className="text-[11px] text-ink-faint">Current streak</span>
          </div>
          <div className="flex flex-col items-center gap-1">
            <span className="tnum font-display text-2xl font-semibold text-ink">
              {data.longest_streak_days}
            </span>
            <span className="text-[11px] text-ink-faint">Longest streak</span>
          </div>
          {!data.active_today && <p className="text-[12px] text-ink-muted">Nothing logged yet today.</p>}
        </div>
      )}
    </PanelShell>
  );
}

function ProductivityHoursPanel() {
  const { data, error, isLoading } = useSWR("productivity-hours", analyticsApi.productivityHours, {
    shouldRetryOnError: false,
  });

  const maxHours = data ? Math.max(1, ...data.by_hour.map((b) => b.hours_logged)) : 1;

  return (
    <PanelShell
      eyebrow="GET /api/analytics/productivity-hours"
      title="Productive hours"
      isLoading={isLoading}
      error={error}
      empty={!!data && data.by_hour.every((b) => b.hours_logged === 0)}
      emptyDescription={`Work sessions from the last ${data?.lookback_days ?? 30} days will chart your best hours here.`}
    >
      {data && (
        <div className="flex flex-col gap-3">
          <div className="flex h-24 items-end gap-[3px]">
            {data.by_hour.map((bucket) => (
              <div
                key={bucket.hour}
                className="flex-1 rounded-sm bg-primary/70"
                style={{ height: `${Math.max(4, (bucket.hours_logged / maxHours) * 100)}%` }}
                title={`${bucket.hour}:00 — ${bucket.hours_logged}h across ${bucket.sessions_count} session${
                  bucket.sessions_count === 1 ? "" : "s"
                }`}
              />
            ))}
          </div>
          <div className="flex items-center justify-between text-[11px] text-ink-faint">
            <span>12am</span>
            <span>12pm</span>
            <span>11pm</span>
          </div>
          {data.best_hour != null && (
            <p className="text-[12px] text-ink-muted">
              Most productive around <span className="tnum text-ink">{data.best_hour}:00</span>
            </p>
          )}
        </div>
      )}
    </PanelShell>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: "critical" }) {
  return (
    <div>
      <p className="text-[11px] text-ink-faint">{label}</p>
      <p className={`tnum text-[15px] font-medium ${tone === "critical" ? "text-critical" : "text-ink"}`}>
        {value}
      </p>
    </div>
  );
}

export default function AnalyticsPage() {
  return (
    <>
      <TopBar>
        <h1 className="font-display text-xl font-semibold text-ink">Analytics</h1>
        <p className="mt-0.5 text-[13px] text-ink-muted">
          Weekly review, estimation error, streaks, productive hours, and workload.
        </p>
      </TopBar>

      <main className="flex-1 p-6 md:p-8">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <WeeklyReviewPanel />
          <WorkloadHeatmap />
          <EstimationErrorPanel />
          <StreaksPanel />
          <ProductivityHoursPanel />
        </div>
      </main>
    </>
  );
}
