"use client";

import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { Bell } from "lucide-react";
import { notificationsApi } from "@/services/api";
import { NotificationSeverity } from "@/services/types";
import { cn } from "@/lib/format";

const DOT_TONE: Record<NotificationSeverity, string> = {
  info: "bg-ink-faint",
  warning: "bg-risk",
  critical: "bg-critical",
};

/**
 * Surfaces the Notification System (PRD §27 / services/notification_service.py)
 * as a bell in the top bar. Notifications are computed live from current
 * state (schedule, deadlines, clock) on every GET, so a short poll interval
 * keeps this reasonably fresh without needing a websocket.
 */
export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const { data } = useSWR("notifications", () => notificationsApi.list(), {
    refreshInterval: 60_000,
    shouldRetryOnError: false,
  });

  const notifications = data?.notifications ?? [];
  const highestSeverity: NotificationSeverity | null = notifications.some(
    (n) => n.severity === "critical"
  )
    ? "critical"
    : notifications.some((n) => n.severity === "warning")
    ? "warning"
    : notifications.length > 0
    ? "info"
    : null;

  useEffect(() => {
    if (!open) return;
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label="Notifications"
        className="relative flex h-8 w-8 items-center justify-center rounded-full border border-hairline bg-surface text-ink-muted transition-colors hover:text-ink"
      >
        <Bell size={14} />
        {highestSeverity && (
          <span
            className={cn(
              "absolute right-1 top-1 h-1.5 w-1.5 rounded-full",
              DOT_TONE[highestSeverity]
            )}
          />
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-20 mt-2 w-80 rounded-panel border border-hairline bg-surface shadow-panel">
          <div className="border-b border-hairline px-4 py-3">
            <p className="font-display text-[13px] font-medium text-ink">Notifications</p>
          </div>
          {notifications.length === 0 ? (
            <p className="px-4 py-6 text-center text-[13px] text-ink-faint">
              Nothing needs your attention right now.
            </p>
          ) : (
            <ul className="max-h-80 divide-y divide-hairline overflow-y-auto">
              {notifications.map((n, i) => (
                <li key={i} className="flex items-start gap-2.5 px-4 py-3">
                  <span
                    className={cn(
                      "mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full",
                      DOT_TONE[n.severity]
                    )}
                  />
                  <div>
                    <p className="text-[13px] text-ink">{n.message}</p>
                    {n.action && (
                      <p className="mt-0.5 text-[11px] text-ink-faint">{n.action}</p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
