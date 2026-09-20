"use client";

import { useState } from "react";
import { useSWRConfig } from "swr";
import { demoApi } from "@/services/api";
import { useProjects } from "@/hooks/useProjects";
import { useToast } from "@/components/ui/Toast";
import { friendlyApiError } from "@/lib/format";

/** Prefix backend/services/demo_service.py stamps on every synthetic project. */
export const DEMO_PREFIX = "[Demo]";

/**
 * Load / reset the labeled demo workspace. Both operations change data
 * that nearly every screen reads (tasks, projects, next-task, analytics,
 * calibration), so after either one every SWR key is revalidated rather
 * than trying to enumerate which caches are affected.
 */
export function useDemoWorkspace() {
  const { projects } = useProjects();
  const { mutate } = useSWRConfig();
  const toast = useToast();
  const [busy, setBusy] = useState<"seed" | "reset" | null>(null);

  const isLoaded = projects.some((p) => p.name.startsWith(DEMO_PREFIX));

  const run = async (kind: "seed" | "reset") => {
    if (busy) return null;
    setBusy(kind);
    try {
      const result = kind === "seed" ? await demoApi.seed() : await demoApi.reset();
      await mutate(() => true);
      return result;
    } catch (err) {
      toast.error(
        friendlyApiError(
          err,
          kind === "seed" ? "Couldn't load the demo workspace." : "Couldn't reset the demo workspace."
        )
      );
      return null;
    } finally {
      setBusy(null);
    }
  };

  return {
    isLoaded,
    busy,
    seed: () => run("seed"),
    reset: () => run("reset"),
  };
}
