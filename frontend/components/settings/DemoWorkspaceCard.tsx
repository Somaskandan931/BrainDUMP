"use client";

import { useState } from "react";
import { FlaskConical } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { useDemoWorkspace } from "@/hooks/useDemo";
import { DemoSeedResponse } from "@/services/types";

/** Compact one-click loader, reused as the dashboard's empty-state action. */
export function LoadDemoButton({ size = "md" }: { size?: "sm" | "md" }) {
  const { isLoaded, busy, seed } = useDemoWorkspace();
  if (isLoaded) return null;
  return (
    <Button variant="secondary" size={size} loading={busy === "seed"} onClick={() => seed()}>
      {busy !== "seed" && <FlaskConical size={14} />}
      Load demo workspace
    </Button>
  );
}

/**
 * Settings section for the demo workspace. Everything it creates is
 * prefixed "[Demo]" and removed again by Reset without touching real
 * projects, tasks or analytics (backend/services/demo_service.py).
 */
export function DemoWorkspaceCard() {
  const { isLoaded, busy, seed, reset } = useDemoWorkspace();
  const [lastSeed, setLastSeed] = useState<DemoSeedResponse | null>(null);

  const handleSeed = async () => {
    const result = await seed();
    if (result) setLastSeed(result as DemoSeedResponse);
  };

  const handleReset = async () => {
    await reset();
    setLastSeed(null);
  };

  return (
    <Card>
      <CardHeader
        eyebrow="Try it out"
        title="Demo workspace"
        action={isLoaded ? <Badge tone="primary">Loaded</Badge> : undefined}
      />
      <p className="mb-3 text-[13px] text-ink-muted">
        Generates about three weeks of synthetic history — projects, completed tasks that ran over
        or under their estimates, work sessions, and daily metrics — so calibration, the
        &ldquo;Why…?&rdquo; explanations, streaks and the execution score have something to show
        on a fresh install. Everything is prefixed{" "}
        <code className="tnum text-ink">[Demo]</code> and Reset removes it without touching your
        real data.
      </p>

      {lastSeed && !lastSeed.already_seeded && (
        <p className="tnum mb-3 text-[12px] text-ink-muted">
          Created {lastSeed.projects_created} projects, {lastSeed.tasks_completed} completed and{" "}
          {lastSeed.tasks_pending} open tasks, and {lastSeed.metrics_days} days of metrics.
        </p>
      )}

      <div className="flex gap-2">
        <Button variant="primary" loading={busy === "seed"} disabled={isLoaded} onClick={handleSeed}>
          Load demo workspace
        </Button>
        <Button variant="danger" loading={busy === "reset"} disabled={!isLoaded} onClick={handleReset}>
          Reset demo data
        </Button>
      </div>
    </Card>
  );
}
