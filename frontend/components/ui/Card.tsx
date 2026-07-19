import { cn } from "@/lib/format";
import { HTMLAttributes, ReactNode } from "react";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  padded?: boolean;
}

/** The one structural unit of every panel on the dashboard: a hairline
 * border, a slightly raised surface, nothing louder than that. */
export function Card({ children, className, padded = true, ...rest }: CardProps) {
  return (
    <div
      className={cn(
        "rounded-panel border border-hairline bg-surface shadow-panel",
        padded && "p-5",
        className
      )}
      {...rest}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  eyebrow,
  action,
}: {
  title: string;
  eyebrow?: string;
  action?: ReactNode;
}) {
  return (
    <div className="mb-4 flex items-start justify-between gap-3">
      <div>
        {eyebrow && (
          <div className="mb-1 text-[11px] font-medium uppercase tracking-[0.14em] text-ink-faint">
            {eyebrow}
          </div>
        )}
        <h2 className="font-display text-[15px] font-medium text-ink">{title}</h2>
      </div>
      {action}
    </div>
  );
}
