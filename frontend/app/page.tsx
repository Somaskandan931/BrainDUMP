"use client";

import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { TopBar } from "@/components/layout/TopBar";
import { Card, CardHeader } from "@/components/ui/Card";
import { NextBestTaskCard } from "@/components/dashboard/NextBestTaskCard";
import { ExecutionScoreCard } from "@/components/dashboard/ExecutionScoreCard";
import { DueTodayCard } from "@/components/dashboard/DueTodayCard";
import { TaskQuickAddPanel } from "@/components/dashboard/TaskQuickAddPanel";
import { DeadlinesPanel } from "@/components/dashboard/DeadlinesPanel";
import { DeadlineRiskCard } from "@/components/dashboard/DeadlineRiskCard";
import { ScheduleChangeCard } from "@/components/dashboard/ScheduleChangeCard";
import { WorkloadHeatmap } from "@/components/dashboard/WorkloadHeatmap";
import { useProjects } from "@/hooks/useProjects";
import { useDailySummary } from "@/hooks/usePlanner";

export default function DashboardPage() {
  const { projects } = useProjects("active");
  const { summary } = useDailySummary();

  const subtitle =
    summary?.narration ??
    (projects.length > 0
      ? `${projects.length} active project${projects.length === 1 ? "" : "s"}`
      : "No active projects yet — add your first task below.");

  return (
    <>
      <TopBar>
        <h1 className="font-display text-xl font-semibold text-ink">Today</h1>
        <p className="mt-0.5 text-[13px] text-ink-muted">{subtitle}</p>
      </TopBar>

      <main className="flex-1 p-6 md:p-8">
        {/* Primary "Today" surface: add tasks, drag to prioritize on the
            left, the computed deadline schedule with buffers on the
            right — this is the pair the whole dashboard is built around. */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <TaskQuickAddPanel />
          <DeadlinesPanel />
        </div>

        {/* Everything else — execution score, next-best-task, workload,
            risk — stays available but demoted below the fold so it
            doesn't compete with the Today surface above. */}
        <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="flex flex-col gap-4 lg:col-span-2">
            <ExecutionScoreCard />
            <NextBestTaskCard />
            <DueTodayCard />
          </div>

          <div className="flex flex-col gap-4">
            <DeadlineRiskCard />
            <ScheduleChangeCard />
            <WorkloadHeatmap />

            <Card>
              <CardHeader eyebrow="Analytics" title="Weekly review" />
              <p className="text-[13px] text-ink-muted">
                Estimation error, streaks, and productive-hour analysis — full
                breakdown on the analytics page.
              </p>
              <Link
                href="/analytics"
                className="mt-3 inline-flex items-center gap-1 text-[13px] font-medium text-primary-hover hover:text-primary"
              >
                View analytics <ArrowUpRight size={13} />
              </Link>
            </Card>
          </div>
        </div>
      </main>
    </>
  );
}
