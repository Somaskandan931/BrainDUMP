import { Loader2 } from "lucide-react";

/** Plain-language reasons from the explanation service. Shared by every
 * "Why…?" panel so they read the same way. */
export function ReasonList({ reasons }: { reasons: string[] }) {
  if (reasons.length === 0) return null;
  return (
    <ul className="flex flex-col gap-1.5">
      {reasons.map((reason, i) => (
        <li key={i} className="flex gap-2 text-[12px] leading-relaxed text-ink-muted">
          <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-primary" aria-hidden="true" />
          <span>{reason}</span>
        </li>
      ))}
    </ul>
  );
}

export function ExplainLoading({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2 py-2 text-[12px] text-ink-faint">
      <Loader2 size={13} className="animate-spin" />
      {label}
    </div>
  );
}

export function ExplainError({ message }: { message: string }) {
  return <p className="py-2 text-[12px] text-ink-faint">{message}</p>;
}
