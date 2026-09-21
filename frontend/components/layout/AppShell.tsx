"use client";

import { usePathname } from "next/navigation";
import { ReactNode } from "react";
import { Sidebar } from "@/components/layout/Sidebar";
import { RouteGuard } from "@/components/layout/RouteGuard";

const PUBLIC_PATHS = new Set(["/login", "/register", "/auth/github/callback"]);

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const isPublic = PUBLIC_PATHS.has(pathname ?? "");

  return (
    <RouteGuard>
      {isPublic ? (
        children
      ) : (
        <>
          <Sidebar />
          <div className="flex min-w-0 flex-1 flex-col overflow-y-auto">{children}</div>
        </>
      )}
    </RouteGuard>
  );
}
