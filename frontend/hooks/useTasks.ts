"use client";

import useSWR from "swr";
import { tasksApi } from "@/services/api";
import { Task, TaskCreate, TaskUpdate } from "@/services/types";

export function useTasks(params?: { projectId?: number; statusFilter?: string }) {
  const key = ["tasks", params?.projectId ?? null, params?.statusFilter ?? null];
  const { data, error, isLoading, mutate } = useSWR<Task[]>(key, () =>
    tasksApi.list(params)
  );

  return {
    tasks: data ?? [],
    isLoading,
    error,
    refresh: mutate,
    create: async (payload: TaskCreate) => {
      const created = await tasksApi.create(payload);
      await mutate();
      return created;
    },
    update: async (id: number, payload: TaskUpdate) => {
      const updated = await tasksApi.update(id, payload);
      await mutate();
      return updated;
    },
    complete: async (id: number) => {
      const done = await tasksApi.complete(id);
      await mutate();
      return done;
    },
    remove: async (id: number) => {
      await tasksApi.remove(id);
      await mutate();
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
