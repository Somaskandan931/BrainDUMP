"use client";

import useSWR from "swr";
import { calendarApi, plannerApi } from "@/services/api";

export function useNextTask() {
  const { data, error, isLoading, mutate } = useSWR(
    "next-task",
    () => plannerApi.nextTask(),
    { refreshInterval: 60_000 }
  );

  return {
    task: data?.task ?? null,
    isLoading,
    error,
    refresh: mutate,
  };
}

export function useCalendarEvents(source?: string) {
  const { data, error, isLoading, mutate } = useSWR(
    ["calendar-events", source ?? null],
    () => calendarApi.events(source),
    { refreshInterval: 5 * 60_000 }
  );

  return { events: data ?? [], isLoading, error, refresh: mutate };
}
