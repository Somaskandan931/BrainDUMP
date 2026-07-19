"use client";

import useSWR from "swr";
import { healthApi } from "@/services/api";
import { cn } from "@/lib/format";

/** The whole app is one FastAPI process on localhost — if it's down,
 * every page below this fails the same way, so say so once, here,
 * rather than repeating a fetch-failed message on every card. */
export function ConnectionStatus() {
  const { data, error, isLoading } = useSWR(
    "health",
    () => healthApi.check(),
    { refreshInterval: 15_000, shouldRetryOnError: true }
  );

  const ok = !!data && !error;
  const label = isLoading ? "Checking backend…" : ok ? "Backend online" : "Backend unreachable";

  return (
    <div className="flex items-center gap-2 rounded-full border border-hairline bg-surface px-3 py-1.5">
      <span
        className={cn(
          "h-1.5 w-1.5 rounded-full",
          ok ? "bg-signal" : isLoading ? "bg-ink-faint" : "bg-critical"
        )}
      />
      <span className="text-[11px] font-medium text-ink-muted">{label}</span>
    </div>
  );
}
