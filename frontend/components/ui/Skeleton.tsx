import { cn } from "@/lib/format";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-surface-raised", className)}
      aria-hidden="true"
    />
  );
}
