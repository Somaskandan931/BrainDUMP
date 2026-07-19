"use client";

import useSWR from "swr";
import { projectsApi } from "@/services/api";
import { Project, ProjectCreate, ProjectUpdate } from "@/services/types";

export function useProjects(statusFilter?: string) {
  const { data, error, isLoading, mutate } = useSWR<Project[]>(
    ["projects", statusFilter],
    () => projectsApi.list(statusFilter),
    { revalidateOnFocus: true }
  );

  return {
    projects: data ?? [],
    isLoading,
    error,
    refresh: mutate,
    create: async (payload: ProjectCreate) => {
      const created = await projectsApi.create(payload);
      await mutate();
      return created;
    },
    update: async (id: number, payload: ProjectUpdate) => {
      const updated = await projectsApi.update(id, payload);
      await mutate();
      return updated;
    },
    remove: async (id: number) => {
      await projectsApi.remove(id);
      await mutate();
    },
  };
}

export function useProject(id: number | null) {
  const { data, error, isLoading, mutate } = useSWR<Project>(
    id != null ? ["project", id] : null,
    () => projectsApi.get(id as number)
  );

  return { project: data, isLoading, error, refresh: mutate };
}
