import { differenceInCalendarDays, format, formatDistanceToNowStrict, isPast } from "date-fns";
import { Importance, TaskStatus } from "@/services/types";

export function formatHours(hours: number | null | undefined): string {
  if (hours == null) return "—";
  if (hours < 1) return `${Math.round(hours * 60)}m`;
  const whole = Math.floor(hours);
  const mins = Math.round((hours - whole) * 60);
  return mins === 0 ? `${whole}h` : `${whole}h ${mins}m`;
}

export function formatPercent(value: number | null | undefined, digits = 0): string {
  if (value == null) return "—";
  const pct = value <= 1 ? value * 100 : value;
  return `${pct.toFixed(digits)}%`;
}

export function formatDeadline(deadline: string | null): {
  label: string;
  urgent: boolean;
  overdue: boolean;
} {
  if (!deadline) return { label: "No deadline", urgent: false, overdue: false };
  const date = new Date(deadline);
  const days = differenceInCalendarDays(date, new Date());
  const overdue = isPast(date) && days < 0;

  if (overdue) return { label: `Overdue · ${format(date, "MMM d")}`, urgent: true, overdue: true };
  if (days === 0) return { label: "Today", urgent: true, overdue: false };
  if (days === 1) return { label: "Tomorrow", urgent: true, overdue: false };
  if (days <= 6) return { label: `${days} days`, urgent: days <= 2, overdue: false };
  return { label: format(date, "MMM d"), urgent: false, overdue: false };
}

export function timeAgo(iso: string): string {
  return formatDistanceToNowStrict(new Date(iso), { addSuffix: true });
}

export const IMPORTANCE_ORDER: Record<Importance, number> = {
  critical: 3,
  high: 2,
  medium: 1,
  low: 0,
};

export const STATUS_LABEL: Record<TaskStatus, string> = {
  pending: "Pending",
  in_progress: "In progress",
  blocked: "Blocked",
  completed: "Completed",
  cancelled: "Cancelled",
};

export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/**
 * Turn a caught error from services/api.ts into something safe to show a
 * user in a toast. status === 0 means the fetch itself failed (backend
 * unreachable) — that's the ApiError.message already crafted for humans.
 */
export function friendlyApiError(err: unknown, fallback: string): string {
  if (err instanceof Error && err.name === "ApiError") {
    return err.message;
  }
  return fallback;
}
