"use client";

import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { TopBar } from "@/components/layout/TopBar";
import { Card, CardHeader } from "@/components/ui/Card";
import { NextBestTaskCard } from "@/components/dashboard/NextBestTaskCard";
import { DueTodayCard } from "@/components/dashboard/DueTodayCard";
import { DeadlineRiskCard } from "@/components/dashboard/DeadlineRiskCard";
import { BrainDumpForm } from "@/components/dashboard/BrainDumpForm";
import { useProjects } from "@/hooks/useProjects";

function greeting(): string {
  const hour = new Date().getHours();
  if (hour < 5) return "Still up";
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export default function DashboardPage() {
  const { projects } = useProjects("active");

  return (
    <>
      <TopBar>
        <h1 className="font-display text-xl font-semibold text-ink">
          {greeting()}
          <span className="text-ink-faint">.</span>
        </h1>
        <p className="mt-0.5 text-[13px] text-ink-muted">
          {projects.length > 0
            ? `${projects.length} active project${projects.length === 1 ? "" : "s"}`
            : "No active projects yet — start with a brain dump below."}
        </p>
      </TopBar>

      <main className="grid flex-1 grid-cols-1 gap-4 p-6 md:p-8 lg:grid-cols-3">
        <div className="flex flex-col gap-4 lg:col-span-2">
          <NextBestTaskCard />
          <DueTodayCard />

          <Card>
            <CardHeader eyebrow="POST /api/planner/brain-dump" title="Quick brain dump" />
            <BrainDumpForm compact />
          </Card>
        </div>

        <div className="flex flex-col gap-4">
          <DeadlineRiskCard />

          <Card>
            <CardHeader eyebrow="Milestone 8" title="Weekly review" />
            <p className="text-[13px] text-ink-muted">
              Estimation error, streaks, and productive-hour analysis land once the
              analytics pipeline is built.
            </p>
            <Link
              href="/analytics"
              className="mt-3 inline-flex items-center gap-1 text-[13px] font-medium text-primary-hover hover:text-primary"
            >
              View analytics <ArrowUpRight size={13} />
            </Link>
          </Card>
        </div>
      </main>
    </>
  );
}
