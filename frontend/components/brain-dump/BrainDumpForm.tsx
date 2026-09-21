"use client";

import { FormEvent, useState } from "react";
import { Loader2, Wand2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { plannerApi } from "@/services/api";
import { ApiError, BrainDumpResponse } from "@/services/types";

export function BrainDumpForm({
  compact = false,
  onDone,
}: {
  compact?: boolean;
  onDone?: () => void;
}) {
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BrainDumpResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await plannerApi.brainDump(text.trim());
      setResult(res);
      setText("");
      onDone?.();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Couldn't reach the brain-dump agent. Check the backend is running and Ollama is up."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Need to finish CV assignment&#10;Build supplier API&#10;Gym tomorrow&#10;Interview next Friday"
        rows={compact ? 3 : 6}
        className="w-full resize-none rounded-md border border-hairline bg-surface-raised px-3 py-2.5 text-[13px] text-ink placeholder:text-ink-faint focus:border-primary focus:outline-none"
      />
      <div className="flex items-center justify-between">
        <span className="text-[11px] text-ink-faint">
          One thought per line works best — the parser splits and groups them.
        </span>
        <Button type="submit" variant="primary" size="sm" disabled={!text.trim() || loading}>
          {loading ? <Loader2 size={14} className="animate-spin" /> : <Wand2 size={14} />}
          {loading ? "Parsing…" : "Dump it"}
        </Button>
      </div>

      {error && (
        <p className="rounded-md border border-critical/30 bg-critical-dim px-3 py-2 text-[12px] text-critical">
          {error}
        </p>
      )}

      {result && (result.projects.length > 0 || result.tasks.length > 0) && (
        <div className="rounded-md border border-hairline bg-surface-overlay p-3">
          <p className="mb-2 text-[11px] font-medium uppercase tracking-wide text-ink-faint">
            Created from that dump
          </p>
          <div className="flex flex-wrap gap-1.5">
            {result.projects.map((p) => (
              <Badge key={`p-${p.id}`} tone="primary">
                {p.name}
              </Badge>
            ))}
            {result.tasks.map((t) => (
              <Badge key={`t-${t.id}`} tone="neutral">
                {t.title}
              </Badge>
            ))}
          </div>
        </div>
      )}
    </form>
  );
}
