"use client";

import useSWR from "swr";
import { settingsApi } from "@/services/api";
import { TimeBlockCreate, UserSettingsUpdate } from "@/services/types";
import { useToast } from "@/components/ui/Toast";
import { friendlyApiError } from "@/lib/format";

export function useSettings() {
  const { data, error, isLoading, mutate } = useSWR("settings", () => settingsApi.get());
  const toast = useToast();

  return {
    settings: data ?? null,
    isLoading,
    error,
    refresh: mutate,
    update: async (payload: UserSettingsUpdate) => {
      try {
        const updated = await settingsApi.update(payload);
        await mutate(updated, { revalidate: false });
        return updated;
      } catch (err) {
        toast.error(friendlyApiError(err, "Couldn't save settings."));
        return null;
      }
    },
  };
}

export function useTimeBlocks() {
  const { data, error, isLoading, mutate } = useSWR("time-blocks", () => settingsApi.timeBlocks());
  const toast = useToast();

  return {
    timeBlocks: data ?? [],
    isLoading,
    error,
    refresh: mutate,
    create: async (payload: TimeBlockCreate) => {
      try {
        const created = await settingsApi.createTimeBlock(payload);
        await mutate();
        return created;
      } catch (err) {
        toast.error(friendlyApiError(err, "Couldn't add that time block."));
        return null;
      }
    },
    remove: async (id: string) => {
      try {
        await settingsApi.removeTimeBlock(id);
        await mutate();
      } catch (err) {
        toast.error(friendlyApiError(err, "Couldn't remove that time block."));
      }
    },
  };
}
