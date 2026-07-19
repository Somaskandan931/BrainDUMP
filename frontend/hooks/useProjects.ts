"use client";

import useSWR from "swr";
import { projectsApi } from "@/services/api";
import { Project, ProjectCreate, ProjectUpdate } from "@/services/types";
import { useToast } from "@/components/ui/Toast";
import { friendlyApiError } from "@/lib/format";

export function useProjects(statusFilter?: string) {
  const { data, error, isLoading, mutate } = useSWR<Project[]>(
    ["projects", statusFilter],
    () => projectsApi.list(statusFilter),
    { revalidateOnFocus: true }
  );
  const toast = useToast();

  return {
    projects: data ?? [],
    isLoading,
    error,
    refresh: mutate,
    create: async (payload: ProjectCreate) => {
      try {
        const created = await projectsApi.create(payload);
        await mutate();
        return created;
      } catch (err) {
        toast.error(friendlyApiError(err, "Couldn't create the project."));
        return null;
      }
    },
    update: async (id: number, payload: ProjectUpdate) => {
      try {
        const updated = await projectsApi.update(id, payload);
        await mutate();
        return updated;
      } catch (err) {
        toast.error(friendlyApiError(err, "Couldn't update the project."));
        return null;
      }
    },
    remove: async (id: number) => {
      try {
        await projectsApi.remove(id);
        await mutate();
      } catch (err) {
        toast.error(friendlyApiError(err, "Couldn't delete the project."));
      }
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
