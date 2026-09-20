"use client";

import useSWR from "swr";
import { ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { RadialGauge } from "./RadialGauge";
import { analyticsApi } from "@/services/api";
import { ExecutionScoreBand } from "@/services/types";
import { cn } from "@/lib/format";

const BAND_TONE: Record<ExecutionScoreBand, "signal" | "primary" | "risk" | "critical"> = {
  excellent: "signal",
  healthy: "primary",
  busy: "risk",
  high_risk: "risk",
  impossible: "critical",
};

const COMPONENT_LABEL: Record<string, string> = {
  capacity: "Capacity",
  deadline_safety: "Deadline safety",
  buffer: "Buffer",
  workload_balance: "Workload balance",
  calendar_stability: "Calendar stability",
  completion_confidence: "Completion confidence",
};

/**
 * PRD §15's "one feature I'd add that can differentiate BrainDUMP" and
 * §37's dashboard hero section — a single 0-100 number answering "is
 * today's plan realistic?" instead of making the user infer that from
 * a task list. See services/execution_score_service.py for how the
 * score is actually composed; this card doesn't recompute anything,
 * it just renders what the backend already decided and lets the user
 * expand into why.
 */
export function ExecutionScoreCard() {
  const [expanded, setExpanded] = useState(false);
  const { data, isLoading } = useSWR(
    "execution-score",
    () => analyticsApi.executionScore(),
    { refreshInterval: 60_000, shouldRetryOnError: false }
  );

  if (isLoading || !data) {
    return (
      <Card className="flex items-center gap-5">
        <Skeleton className="h-[100px] w-[100px] shrink-0 rounded-full" />
        <div className="flex-1">
          <Skeleton className="mb-2 h-4 w-40" />
          <Skeleton className="h-3 w-56" />
        </div>
      </Card>
    );
  }

  const tone = BAND_TONE[data.band];

  return (
    <Card>
      <div className="flex items-center gap-5">
        <RadialGauge value={data.score} size={100} stroke={8} tone={tone} suffix="" />
        <div className="min-w-0 flex-1">
          <div className="mb-1 text-[11px] font-medium uppercase tracking-[0.14em] text-ink-faint">
            Execution score
          </div>
          <p className="font-display text-[15px] font-medium text-ink">{data.headline}</p>
          <button
            onClick={() => setExpanded((e) => !e)}
            className="mt-2 inline-flex items-center gap-1 text-[12px] text-ink-faint hover:text-ink-muted"
          >
            {expanded ? "Hide breakdown" : "Why?"}
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>
        </div>
      </div>

      {expanded && (
        <ul className="mt-4 flex flex-col gap-2 border-t border-hairline pt-4">
          {data.components.map((c) => (
            <li key={c.name} className="flex items-center gap-3">
              <span className="w-[150px] shrink-0 text-[11px] font-medium text-ink-muted">
                {COMPONENT_LABEL[c.name] ?? c.name}
              </span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-raised">
                <div
                  className={cn(
                    "h-full rounded-full",
                    c.score >= 65 ? "bg-signal" : c.score >= 40 ? "bg-risk" : "bg-critical"
                  )}
                  style={{ width: `${Math.max(0, Math.min(100, c.score))}%` }}
                />
              </div>
              <span className="w-[220px] shrink-0 truncate text-[11px] text-ink-faint" title={c.detail}>
                {c.detail}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
