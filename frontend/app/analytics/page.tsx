"use client";

import useSWR from "swr";
import { Construction, LineChart } from "lucide-react";
import { TopBar } from "@/components/layout/TopBar";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { analyticsApi } from "@/services/api";
import { ApiError } from "@/services/types";

function AnalyticsPanel({
  eyebrow,
  title,
  fetcher,
}: {
  eyebrow: string;
  title: string;
  fetcher: () => Promise<unknown>;
}) {
  const { data, error, isLoading } = useSWR([eyebrow], fetcher, { shouldRetryOnError: false });
  const notBuilt = error instanceof ApiError && error.status === 501;

  return (
    <Card>
      <CardHeader eyebrow={eyebrow} title={title} />
      {isLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : notBuilt ? (
        <EmptyState
          icon={<Construction size={18} />}
          title="Not built yet"
          description="Milestone 8 (Analytics and ML components) wires this up against backend/models/metrics.py."
        />
      ) : error ? (
        <p className="text-[13px] text-critical">{(error as Error).message}</p>
      ) : (
        <pre className="overflow-x-auto rounded-md bg-surface-raised p-3 text-[12px] text-ink-muted">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </Card>
  );
}

export default function AnalyticsPage() {
  return (
    <>
      <TopBar>
        <h1 className="font-display text-xl font-semibold text-ink">Analytics</h1>
        <p className="mt-0.5 text-[13px] text-ink-muted">
          Weekly review, estimation error, streaks, productive hours.
        </p>
      </TopBar>

      <main className="flex-1 p-6 md:p-8">
        <div className="mb-4 flex items-center gap-2 rounded-md border border-hairline bg-surface px-4 py-3">
          <LineChart size={16} className="text-primary" />
          <p className="text-[13px] text-ink-muted">
            These panels call the real <span className="tnum text-ink">/api/analytics/*</span>{" "}
            routes — right now they return <span className="text-ink">501</span> by design
            (see <span className="text-ink">backend/api/analytics.py</span>). They&apos;ll fill in
            with no frontend changes once Milestone 8 lands.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <AnalyticsPanel
            eyebrow="GET /api/analytics/weekly-review"
            title="Weekly review"
            fetcher={analyticsApi.weeklyReview}
          />
          <AnalyticsPanel
            eyebrow="GET /api/analytics/estimation-error"
            title="Estimation error"
            fetcher={analyticsApi.estimationError}
          />
          <AnalyticsPanel
            eyebrow="GET /api/analytics/streaks"
            title="Streaks"
            fetcher={analyticsApi.streaks}
          />
          <AnalyticsPanel
            eyebrow="GET /api/analytics/productivity-hours"
            title="Productivity by hour"
            fetcher={analyticsApi.productivityHours}
          />
        </div>
      </main>
    </>
  );
}
