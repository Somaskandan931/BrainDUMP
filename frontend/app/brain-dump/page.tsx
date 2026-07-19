"use client";

import { FormEvent, useState } from "react";
import { Loader2, Target } from "lucide-react";
import { TopBar } from "@/components/layout/TopBar";
import { Card, CardHeader } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { BrainDumpForm } from "@/components/dashboard/BrainDumpForm";
import { plannerApi } from "@/services/api";
import { ApiError, GoalResponse } from "@/services/types";

function GoalEngine() {
  const [goal, setGoal] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<GoalResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!goal.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await plannerApi.goal(goal.trim());
      setResult(res);
      setGoal("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't reach the goal agent.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card>
      <CardHeader eyebrow="POST /api/planner/goal" title="Goal engine" />
      <p className="mb-3 text-[13px] text-ink-muted">
        One outcome in, a whole project with a task roadmap out — e.g.{" "}
        <span className="text-ink-faint">&quot;Get placed as an AI engineer&quot;</span>.
      </p>
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <input
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="Get placed as an AI engineer"
          className="w-full rounded-md border border-hairline bg-surface-raised px-3 py-2.5 text-[13px] text-ink placeholder:text-ink-faint focus:border-primary focus:outline-none"
        />
        <div className="flex justify-end">
          <Button type="submit" variant="primary" size="sm" disabled={!goal.trim() || loading}>
            {loading ? <Loader2 size={14} className="animate-spin" /> : <Target size={14} />}
            {loading ? "Building roadmap…" : "Build roadmap"}
          </Button>
        </div>
      </form>

      {error && (
        <p className="mt-3 rounded-md border border-critical/30 bg-critical-dim px-3 py-2 text-[12px] text-critical">
          {error}
        </p>
      )}

      {result && (
        <div className="mt-4 rounded-md border border-hairline bg-surface-overlay p-3">
          <div className="mb-2 flex items-center gap-2">
            <Badge tone="primary">{result.project.name}</Badge>
            <span className="text-[11px] text-ink-faint">
              {result.tasks.length} task{result.tasks.length === 1 ? "" : "s"} generated
            </span>
          </div>
          <ul className="flex flex-col gap-1">
            {result.tasks.map((t) => (
              <li key={t.id} className="text-[13px] text-ink-muted">
                · {t.title}
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}

export default function BrainDumpPage() {
  return (
    <>
      <TopBar>
        <h1 className="font-display text-xl font-semibold text-ink">Brain Dump</h1>
        <p className="mt-0.5 text-[13px] text-ink-muted">
          Type whatever&apos;s in your head. The parser splits it into projects and tasks —
          no folders, no manual sorting.
        </p>
      </TopBar>

      <main className="grid flex-1 grid-cols-1 gap-4 p-6 md:p-8 lg:grid-cols-2">
        <Card>
          <CardHeader eyebrow="POST /api/planner/brain-dump" title="Dump your thoughts" />
          <BrainDumpForm />
        </Card>

        <GoalEngine />
      </main>
    </>
  );
}
