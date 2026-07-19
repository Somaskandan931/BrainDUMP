"use client";

import useSWR from "swr";
import { analyticsApi, calendarApi, plannerApi } from "@/services/api";

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

/**
 * The Workload Engine (PRD Milestone 4): daily/weekly/monthly capacity
 * vs. allocated hours, for the dashboard heatmap. Refreshes every 5
 * minutes — the schedule doesn't change fast enough to warrant more.
 */
export function useWorkload() {
  const { data, error, isLoading, mutate } = useSWR(
    "workload",
    () => analyticsApi.workload(),
    { refreshInterval: 5 * 60_000 }
  );

  return {
    workload: data ?? null,
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
