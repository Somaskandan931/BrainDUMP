import { AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/Button";

/**
 * A failed fetch is not the same thing as "nothing here yet" and must
 * never be rendered the same way. Every list backed by useTasks()/
 * useProjects() etc. used to fall through to its EmptyState the moment
 * `error` was set (since `data` stays undefined and the hook defaults
 * to `[]`) — a task list that fails to load looked identical to a
 * genuinely empty one, so tasks appeared to "disappear" with no
 * indication anything had gone wrong. Callers should check `error`
 * before checking `length === 0`.
 */
export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-panel border border-dashed border-critical/30 bg-critical-dim px-6 py-8 text-center">
      <AlertCircle size={20} className="text-critical" />
      <p className="font-display text-sm font-medium text-ink">Couldn&apos;t load this</p>
      <p className="max-w-sm text-[13px] text-ink-muted">{message}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" className="mt-1" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  );
}
