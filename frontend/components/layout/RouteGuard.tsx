"use client";

import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect } from "react";
import { useAuth } from "@/lib/auth";

const PUBLIC_PATHS = new Set(["/login", "/register"]);

export function RouteGuard({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const isPublic = PUBLIC_PATHS.has(pathname ?? "");

  useEffect(() => {
    if (loading) return;
    if (!user && !isPublic) router.replace("/login");
    if (user && isPublic) router.replace("/");
  }, [loading, user, isPublic, router]);

  if (isPublic) {
    // /login and /register render full-bleed, no sidebar, regardless of
    // auth state -- the redirect above handles bouncing an already-signed-in
    // user away from them.
    return <>{children}</>;
  }

  if (loading || !user) {
    // Avoid flashing real (unauthenticated) content while we validate the
    // stored token against /api/auth/me, or during the redirect above.
    return (
      <div className="flex h-full w-full items-center justify-center text-sm text-ink/50">
        Loading…
      </div>
    );
  }

  return <>{children}</>;
}
