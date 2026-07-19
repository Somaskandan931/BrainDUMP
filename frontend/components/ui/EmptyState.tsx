import { ReactNode } from "react";

/** Empty and not-yet-built states share one voice: say what's true, say
 * what to do next. Never "no data found" — that's a system phrase, not
 * a Brain Dump one. */
export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-panel border border-dashed border-hairline px-6 py-10 text-center">
      {icon && <div className="mb-1 text-ink-faint">{icon}</div>}
      <p className="font-display text-sm font-medium text-ink">{title}</p>
      {description && <p className="max-w-sm text-[13px] text-ink-muted">{description}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
