"use client";

import { useState } from "react";
import { ArrowRight, HelpCircle, Sparkles } from "lucide-react";
import { Card, CardHeader } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { WhyThisTask } from "@/components/dashboard/WhyThisTask";
import { LoadDemoButton } from "@/components/settings/DemoWorkspaceCard";
import { useNextTask } from "@/hooks/usePlanner";
import { useTasks } from "@/hooks/useTasks";
import { formatHours, formatPercent } from "@/lib/format";

export function NextBestTaskCard() {
  const { task, isLoading, refresh } = useNextTask();
  const { complete } = useTasks();
  const [showWhy, setShowWhy] = useState(false);

  return (
    <Card className="relative overflow-hidden">
      <div className="pointer-events-none absolute -right-10 -top-10 h-40 w-40 rounded-full bg-primary/10 blur-3xl" />
      <CardHeader eyebrow="Priority engine" title="Do next" />

      {isLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : !task ? (
        <EmptyState
          title="Nothing queued right now"
          description="Brain-dump something or add a task with a deadline and the priority engine will surface what to work on next."
          action={<LoadDemoButton size="sm" />}
        />
      ) : (
        <div className="flex flex-col gap-4">
          <div>
            <div className="mb-2 flex items-center gap-2">
              <Sparkles size={14} className="text-primary" />
              <span className="text-[11px] font-medium uppercase tracking-wide text-primary-hover">
                Highest priority
              </span>
            </div>
            <h3 className="font-display text-lg font-medium text-ink">{task.title}</h3>
            {task.description && (
              <p className="mt-1 line-clamp-2 text-[13px] text-ink-muted">{task.description}</p>
            )}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Badge tone="primary">{task.importance}</Badge>
            {task.estimated_hours != null && (
              <Badge tone="neutral">~{formatHours(task.estimated_hours)}</Badge>
            )}
            {task.confidence_score != null && (
              <Badge tone="signal">{formatPercent(task.confidence_score)} confidence</Badge>
            )}
            {task.priority_score != null && (
              <Badge tone="neutral">priority {task.priority_score.toFixed(2)}</Badge>
            )}
            {task.risk_score != null && task.risk_score >= 0.5 && (
              <Badge tone={task.risk_score >= 0.7 ? "critical" : "risk"}>
                {formatPercent(task.risk_score)} risk
              </Badge>
            )}
            {task.completion_probability != null && (
              <Badge tone="signal">{formatPercent(task.completion_probability)} on-time</Badge>
            )}
          </div>

          <div className="flex gap-2 pt-1">
            <Button
              variant="primary"
              onClick={async () => {
                await complete(task.id);
                await refresh();
              }}
            >
              Mark complete
            </Button>
            <Button variant="ghost" onClick={() => refresh()}>
              <ArrowRight size={14} />
              Recalculate
            </Button>
            <Button
              variant="ghost"
              aria-expanded={showWhy}
              onClick={() => setShowWhy((s) => !s)}
            >
              <HelpCircle size={14} />
              Why this task?
            </Button>
          </div>

          {showWhy && <WhyThisTask taskId={task.id} />}
        </div>
      )}
    </Card>
  );
}
