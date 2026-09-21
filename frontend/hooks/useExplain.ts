"use client";

import useSWR, { useSWRConfig } from "swr";
import { analyticsApi, plannerApi, tasksApi } from "@/services/api";
import { ActivityEntry } from "@/services/types";
import { ApiError } from "@/services/types";
import { useToast } from "@/components/ui/Toast";
import { friendlyApiError } from "@/lib/format";

/**
 * Hooks for the explainability layer (backend/services/explanation_service.py).
 *
 * Every hook takes a null id / `enabled: false` to stay idle, so a
 * collapsed "Why…?" panel never pays for a request (same lazy-fetch
 * convention as useDeadlinePlan in hooks/useTasks.ts). Errors are
 * surfaced as `error`, never thrown — a failed explanation must not
 * take down the card it's attached to.
 */

/** "Why this task?" — keyed by task id so it refetches when the
 * recommendation changes underneath an open panel. */
export function useNextTaskExplanation(taskId: number | null) {
  const { data, error, isLoading } = useSWR(
    taskId != null ? ["explain-next-task", taskId] : null,
    () => plannerApi.explainNextTask(),
    { shouldRetryOnError: false }
  );

  return {
    explanation: data?.explanation ?? null,
    isLoading,
    error: error as ApiError | undefined,
  };
}

/** "Why did my schedule change?" plus a manual replan trigger, so the
 * panel can be exercised without waiting for the nightly job. */
export function useScheduleChangeExplanation() {
  const { data, error, isLoading, mutate } = useSWR(
    "explain-replan",
    () => plannerApi.explainReplan(),
    { shouldRetryOnError: false }
  );
  const { mutate: mutateAll } = useSWRConfig();
  const toast = useToast();

  return {
    explanation: data?.explanation ?? null,
    isLoading,
    error: error as ApiError | undefined,
    refresh: mutate,
    /** Runs a real replan, then revalidates everything a replan can change. */
    replan: async () => {
      try {
        const result = await plannerApi.replan();
        await mutateAll(() => true);
        return result;
      } catch (err) {
        toast.error(friendlyApiError(err, "Couldn't replan right now."));
        return null;
      }
    },
  };
}

/** "Why this estimate?" for one task. */
export function useEstimateExplanation(taskId: number | null) {
  const { data, error, isLoading } = useSWR(
    taskId != null ? ["explain-estimate", taskId] : null,
    () => tasksApi.explainEstimate(taskId as number),
    { shouldRetryOnError: false }
  );
  return { explanation: data ?? null, isLoading, error: error as ApiError | undefined };
}

/** "Why is this deadline at risk?" — the backend 400s for a task with
 * no deadline, so callers should only pass an id for tasks that have one. */
export function useDeadlineRiskExplanation(taskId: number | null) {
  const { data, error, isLoading } = useSWR(
    taskId != null ? ["explain-deadline-risk", taskId] : null,
    () => tasksApi.explainDeadlineRisk(taskId as number),
    { shouldRetryOnError: false }
  );
  return { explanation: data ?? null, isLoading, error: error as ApiError | undefined };
}

/** Full audit trail for one task (activity_service.get_entity_history),
 * newest first -- same lazy-fetch convention as the other "Why…?" hooks
 * above, so a collapsed history panel costs nothing until opened. */
export function useTaskHistory(taskId: number | null) {
  const { data, error, isLoading } = useSWR(
    taskId != null ? ["task-history", taskId] : null,
    () => tasksApi.history(taskId as number),
    { shouldRetryOnError: false }
  );
  return {
    entries: (data ?? []) as ActivityEntry[],
    isLoading,
    error: error as ApiError | undefined,
  };
}

/** Per-category bias ml/calibration.py is applying to new estimates right now. */
export function useCalibration() {
  const { data, error, isLoading } = useSWR("calibration", () => analyticsApi.calibration(), {
    shouldRetryOnError: false,
  });
  return {
    categories: data?.categories ?? [],
    isLoading,
    error: error as ApiError | undefined,
  };
}
