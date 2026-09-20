"use client";

import useSWR from "swr";
import { Clock, Flame, LineChart, Repeat, Sparkles, Trophy, TrendingDown, TrendingUp } from "lucide-react";
import { ReactNode } from "react";
import { TopBar } from "@/components/layout/TopBar";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { Badge } from "@/components/ui/Badge";
import { WorkloadHeatmap } from "@/components/dashboard/WorkloadHeatmap";
import { analyticsApi, memoryApi } from "@/services/api";
import { useCalibration } from "@/hooks/useExplain";
import { ApiError, EpisodicEventType, EstimationBias, SemanticRelationType } from "@/services/types";

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
      eyebrow="Analytics engine"
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
      eyebrow="Estimator"
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

function EstimationErrorTrendPanel() {
  const { data, error, isLoading } = useSWR("estimation-error-trend", analyticsApi.estimationErrorTrend, {
    shouldRetryOnError: false,
  });

  const points = data?.points ?? [];
  const maxError = Math.max(1, ...points.map((p) => p.average_error_pct));
  const today = points[points.length - 1];

  return (
    <PanelShell
      eyebrow="Estimator"
      title="Estimation error trend"
      isLoading={isLoading}
      error={error}
      empty={points.length === 0}
      emptyDescription="Complete a few tasks with logged hours over a couple of days and your estimation trend shows up here."
    >
      {points.length > 0 && (
        <div className="flex flex-col gap-3">
          <div className="flex h-24 items-end gap-1.5">
            {points.map((p) => (
              <div key={p.date} className="flex flex-1 flex-col items-center gap-1">
                <div
                  className="w-full rounded-sm bg-risk/70"
                  style={{ height: `${Math.max(4, (p.average_error_pct / maxError) * 100)}%` }}
                  title={`${p.date} — off by ${p.average_error_pct}% on average`}
                />
              </div>
            ))}
          </div>
          <div className="flex items-center justify-between text-[11px] text-ink-faint">
            <span>{points[0]?.date.slice(5)}</span>
            <span>{points[points.length - 1]?.date.slice(5)}</span>
          </div>
          {today && (
            <p className="text-[12px] text-ink-muted">
              Today: <span className="tnum text-ink">{today.average_error_pct}%</span> off on average
            </p>
          )}
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
      eyebrow="Analytics engine"
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
      eyebrow="Analytics engine"
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

function ExecutionScoreTrendPanel() {
  const { data, error, isLoading } = useSWR("execution-score-trend", analyticsApi.executionScoreTrend, {
    shouldRetryOnError: false,
  });

  const TREND_TONE: Record<string, string> = {
    excellent: "bg-signal",
    healthy: "bg-primary",
    busy: "bg-risk",
    high_risk: "bg-risk",
    impossible: "bg-critical",
  };

  const points = data?.points ?? [];
  const today = points[points.length - 1];

  return (
    <PanelShell
      eyebrow="Analytics engine"
      title="Execution score trend"
      isLoading={isLoading}
      error={error}
      empty={points.length === 0}
      emptyDescription="Once the nightly job has run for a day or two, your Execution Score history shows up here."
    >
      {points.length > 0 && (
        <div className="flex flex-col gap-3">
          <div className="flex h-24 items-end gap-1.5">
            {points.map((p) => (
              <div key={p.date} className="flex flex-1 flex-col items-center gap-1">
                <div
                  className={`w-full rounded-sm ${TREND_TONE[p.band] ?? "bg-primary"}`}
                  style={{ height: `${Math.max(4, p.score)}%` }}
                  title={`${p.date} — ${p.score}/100 (${p.band.replace("_", " ")})`}
                />
              </div>
            ))}
          </div>
          <div className="flex items-center justify-between text-[11px] text-ink-faint">
            <span>{points[0]?.date.slice(5)}</span>
            <span>{points[points.length - 1]?.date.slice(5)}</span>
          </div>
          {today && (
            <p className="text-[12px] text-ink-muted">
              Today: <span className="tnum text-ink">{today.score}/100</span> ·{" "}
              {today.band.replace("_", " ")}
            </p>
          )}
        </div>
      )}
    </PanelShell>
  );
}

function EpisodicMemoryPanel() {
  const { data, error, isLoading } = useSWR("episodic-memory", () => memoryApi.episodic(8), {
    shouldRetryOnError: false,
  });

  const EVENT_LABEL: Record<EpisodicEventType, string> = {
    weekly_review: "Weekly review",
    project_completed: "Project completed",
    milestone: "Milestone",
    planning_decision: "Replan",
  };
  const EVENT_TONE: Record<EpisodicEventType, "signal" | "risk" | "neutral"> = {
    weekly_review: "neutral",
    project_completed: "signal",
    milestone: "signal",
    planning_decision: "risk",
  };

  const events = data?.events ?? [];

  return (
    <PanelShell
      eyebrow="Memory engine"
      title="Memory — recent history"
      isLoading={isLoading}
      error={error}
      empty={events.length === 0}
      emptyDescription="Completed projects, weekly reviews, and replans will show up here as they happen."
    >
      <div className="flex flex-col gap-2">
        {events.map((event) => (
          <div
            key={event.id}
            className="flex flex-col gap-0.5 rounded-md border border-hairline bg-surface-raised px-2.5 py-2"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-[12px] text-ink">{event.title}</span>
              <Badge tone={EVENT_TONE[event.event_type]}>{EVENT_LABEL[event.event_type]}</Badge>
            </div>
            <p className="text-[11px] text-ink-faint">{event.summary}</p>
          </div>
        ))}
      </div>
    </PanelShell>
  );
}

function LongTermProfilePanel() {
  const { data, error, isLoading } = useSWR("long-term-memory", memoryApi.longTerm, {
    shouldRetryOnError: false,
  });

  const empty =
    !!data &&
    data.preferred_work_hours.length === 0 &&
    data.estimation_accuracy.sample_count === 0 &&
    data.recent_completed_projects.length === 0;

  return (
    <PanelShell
      eyebrow="Memory engine"
      title="Memory — what BrainDUMP has learned"
      isLoading={isLoading}
      error={error}
      empty={empty}
      emptyDescription="Once the nightly job has run for a few days, your work patterns show up here."
    >
      {data && (
        <div className="flex flex-col gap-3">
          {data.preferred_work_hours.length > 0 && (
            <div className="flex items-center gap-2 text-[12px] text-ink-muted">
              <Clock size={14} className="text-primary-hover" />
              Peak hours:{" "}
              <span className="tnum text-ink">
                {data.preferred_work_hours.map((h) => `${h}:00`).join(", ")}
              </span>
            </div>
          )}
          {data.estimation_accuracy.most_biased_category && (
            <div className="flex items-center gap-2 text-[12px] text-ink-muted">
              <TrendingDown size={14} className="text-risk" />
              Tends to {data.estimation_accuracy.most_biased_direction}{" "}
              <span className="text-ink">{data.estimation_accuracy.most_biased_category}</span>
            </div>
          )}
          {data.recent_completed_projects.length > 0 && (
            <div className="flex items-start gap-2 text-[12px] text-ink-muted">
              <Trophy size={14} className="mt-0.5 shrink-0 text-primary-hover" />
              <span>Recently finished: {data.recent_completed_projects.join(", ")}</span>
            </div>
          )}
          {data.longest_streak_days > 0 && (
            <p className="text-[12px] text-ink-muted">
              Longest streak: <span className="tnum text-ink">{data.longest_streak_days} days</span>
            </p>
          )}
        </div>
      )}
    </PanelShell>
  );
}

function SemanticMemoryPanel() {
  const { data, error, isLoading } = useSWR("semantic-memory", () => memoryApi.semantic(8), {
    shouldRetryOnError: false,
  });

  const RELATION_LABEL: Record<SemanticRelationType, string> = {
    project_template: "Template",
    recurring_workflow: "Recurring",
  };
  const RELATION_TONE: Record<SemanticRelationType, "signal" | "risk" | "neutral"> = {
    project_template: "neutral",
    recurring_workflow: "signal",
  };

  const relations = data?.relations ?? [];

  return (
    <PanelShell
      eyebrow="Memory engine"
      title="Memory — how your work relates"
      isLoading={isLoading}
      error={error}
      empty={relations.length === 0}
      emptyDescription="Templates and recurring workflows show up here once projects are completed."
    >
      <div className="flex flex-col gap-2">
        {relations.map((relation) => (
          <div
            key={relation.id}
            className="flex flex-col gap-0.5 rounded-md border border-hairline bg-surface-raised px-2.5 py-2"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-1.5 text-[12px] text-ink">
                {relation.relation_type === "recurring_workflow" && (
                  <Repeat size={12} className="text-primary-hover" />
                )}
                {relation.title}
              </span>
              <Badge tone={RELATION_TONE[relation.relation_type]}>
                {RELATION_LABEL[relation.relation_type]}
              </Badge>
            </div>
            <p className="text-[11px] text-ink-faint">{relation.summary}</p>
          </div>
        ))}
      </div>
    </PanelShell>
  );
}

/** Personal Calibration (ml/calibration.py): the per-category bias that is
 * being applied to new estimates right now. Bars diverge from a centre
 * line — right = you underestimate (work runs long), left = you overestimate. */
const CALIBRATION_BAR_SCALE_PCT = 60; // matches the backend's clamp, so a full bar means "at the cap"

function CalibrationPanel() {
  const { categories, isLoading, error } = useCalibration();

  return (
    <PanelShell
      eyebrow="Personal calibration"
      title="How your estimates are being corrected"
      isLoading={isLoading}
      error={error}
      empty={categories.length === 0}
      emptyDescription="Once a few tasks in a category have been completed against their estimates, the correction being applied to new estimates shows up here."
    >
      <div className="flex flex-col gap-3">
        {categories.map((c) => {
          const width = Math.min(100, (Math.abs(c.bias_pct) / CALIBRATION_BAR_SCALE_PCT) * 50);
          const under = c.bias_pct > 0;
          return (
            <div key={c.category} className="flex flex-col gap-1">
              <div className="flex items-center justify-between gap-3 text-[12px]">
                <span className="truncate text-ink">{c.category}</span>
                <span className="tnum shrink-0 text-ink-muted">
                  {under ? "+" : ""}
                  {c.bias_pct.toFixed(0)}% · {c.sample_count} tasks
                </span>
              </div>
              <div className="relative h-1.5 overflow-hidden rounded-full bg-surface-overlay">
                <div className="absolute left-1/2 top-0 h-full w-px bg-hairline" />
                <div
                  className={`absolute top-0 h-full rounded-full ${under ? "bg-risk" : "bg-signal"}`}
                  style={under ? { left: "50%", width: `${width}%` } : { right: "50%", width: `${width}%` }}
                />
              </div>
              <p className="text-[11px] text-ink-faint">
                {Math.abs(c.bias_pct) <= 5
                  ? "Estimates here are accurate — no meaningful correction."
                  : under
                    ? "Tasks here run longer than estimated, so new estimates are raised."
                    : "Tasks here finish faster than estimated, so new estimates are lowered."}
              </p>
            </div>
          );
        })}
      </div>
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
          <CalibrationPanel />
          <EstimationErrorTrendPanel />
          <StreaksPanel />
          <ProductivityHoursPanel />
          <ExecutionScoreTrendPanel />
          <EpisodicMemoryPanel />
          <LongTermProfilePanel />
          <SemanticMemoryPanel />
        </div>
      </main>
    </>
  );
}
