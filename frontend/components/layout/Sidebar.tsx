"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  BrainCircuit,
  CalendarDays,
  LayoutDashboard,
  LineChart,
  MessagesSquare,
  Settings,
  SquareKanban,
} from "lucide-react";
import { cn } from "@/lib/format";

const NAV = [
  { href: "/", label: "Today", icon: LayoutDashboard },
  { href: "/brain-dump", label: "Brain Dump", icon: BrainCircuit },
  { href: "/projects", label: "Projects", icon: SquareKanban },
  { href: "/calendar", label: "Calendar", icon: CalendarDays },
  { href: "/analytics", label: "Analytics", icon: LineChart },
  { href: "/chat", label: "AI Chat", icon: MessagesSquare },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden w-[220px] shrink-0 flex-col border-r border-hairline bg-surface/60 px-3 py-5 md:flex">
      <div className="mb-8 flex items-center gap-2.5 px-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary-dim">
          <div className="h-2 w-2 rounded-full bg-primary shadow-[0_0_8px_2px_rgba(124,139,255,0.6)]" />
        </div>
        <div>
          <div className="font-display text-[13px] font-semibold leading-none text-ink">
            Brain Dump
          </div>
          <div className="mt-1 text-[10px] uppercase tracking-[0.12em] text-ink-faint">
            Personal AI OS
          </div>
        </div>
      </div>

      <nav className="flex flex-1 flex-col gap-0.5">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname?.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-2.5 rounded-md px-3 py-2 text-[13px] font-medium transition-colors",
                active
                  ? "bg-primary-dim text-primary-hover"
                  : "text-ink-muted hover:bg-surface-raised hover:text-ink"
              )}
            >
              <Icon size={16} strokeWidth={2} />
              {label}
            </Link>
          );
        })}
      </nav>

      <Link
        href="/settings"
        className={cn(
          "flex items-center gap-2.5 rounded-md px-3 py-2 text-[13px] font-medium transition-colors",
          pathname === "/settings"
            ? "bg-primary-dim text-primary-hover"
            : "text-ink-muted hover:bg-surface-raised hover:text-ink"
        )}
      >
        <Settings size={16} strokeWidth={2} />
        Settings
      </Link>
    </aside>
  );
}
