"use client";

import useSWR from "swr";
import { tasksApi } from "@/services/api";
import { ApiError, Task, TaskCreate, TaskUpdate } from "@/services/types";
import { useToast } from "@/components/ui/Toast";
import { friendlyApiError } from "@/lib/format";

export function useTasks(params?: { projectId?: number; statusFilter?: string }) {
  const key = ["tasks", params?.projectId ?? null, params?.statusFilter ?? null];
  const { data, error, isLoading, mutate } = useSWR<Task[]>(key, () =>
    tasksApi.list(params)
  );
  const toast = useToast();

  return {
    tasks: data ?? [],
    isLoading,
    error,
    refresh: mutate,
    create: async (payload: TaskCreate) => {
      try {
        const created = await tasksApi.create(payload);
        await mutate();
        return created;
      } catch (err) {
        toast.error(friendlyApiError(err, "Couldn't create the task."));
        return null;
      }
    },
    update: async (id: number, payload: TaskUpdate) => {
      try {
        const updated = await tasksApi.update(id, payload);
        await mutate();
        return updated;
      } catch (err) {
        toast.error(friendlyApiError(err, "Couldn't update the task."));
        return null;
      }
    },
    complete: async (id: number) => {
      try {
        const done = await tasksApi.complete(id);
        await mutate();
        return done;
      } catch (err) {
        toast.error(friendlyApiError(err, "Couldn't mark the task complete."));
        return null;
      }
    },
    remove: async (id: number) => {
      try {
        await tasksApi.remove(id);
        await mutate();
      } catch (err) {
        toast.error(friendlyApiError(err, "Couldn't delete the task."));
      }
    },
    reorder: async (orderedIds: number[]) => {
      try {
        // Optimistic: reflect the drag immediately, reconcile with the
        // server's response once it lands (sort_order is now authoritative).
        await mutate(
          async (current) => {
            const reordered = await tasksApi.reorder(orderedIds);
            const byId = new Map(reordered.map((t) => [t.id, t]));
            return (current ?? []).map((t) => byId.get(t.id) ?? t);
          },
          {
            optimisticData: (current) => {
              const byId = new Map((current ?? []).map((t) => [t.id, t]));
              const front = orderedIds.map((id) => byId.get(id)).filter(Boolean) as Task[];
              const rest = (current ?? []).filter((t) => !orderedIds.includes(t.id));
              return [...front, ...rest];
            },
            rollbackOnError: true,
          }
        );
      } catch (err) {
        toast.error(friendlyApiError(err, "Couldn't save the new order."));
      }
    },
  };
}

export function useTask(id: number | null) {
  const { data, error, isLoading, mutate } = useSWR<Task>(
    id != null ? ["task", id] : null,
    () => tasksApi.get(id as number)
  );

  return { task: data, isLoading, error, refresh: mutate };
}

/**
 * The Deadline Engine's buffer plan for one task — fetched only while
 * `taskId` is non-null (SWR's null-key convention), so a collapsed
 * task row never pays for the request. A task with no deadline yields
 * a 400 from the backend; that's surfaced as `error`, not thrown.
 */
export function useDeadlinePlan(taskId: number | null) {
  const { data, error, isLoading } = useSWR(
    taskId != null ? ["deadline-plan", taskId] : null,
    () => tasksApi.deadlinePlan(taskId as number),
    { shouldRetryOnError: false }
  );

  return {
    plan: data,
    isLoading,
    error: error as ApiError | undefined,
  };
}
