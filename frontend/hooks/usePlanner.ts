"use client";

import useSWR from "swr";
import { analyticsApi, calendarApi, plannerApi, scheduleApi } from "@/services/api";

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

/**
 * The dashboard hero payload (PRD §37): last morning job's cached
 * narration + next-task pointer. Refreshes every minute like
 * useNextTask -- it's a cheap read of a `settings` row, not a live
 * Ollama call, so there's no cost to polling it fairly often. Returns
 * null-safe defaults so a brand-new install (no morning run yet) just
 * renders nothing in the hero rather than erroring.
 */
export function useDailySummary() {
  const { data, error, isLoading, mutate } = useSWR(
    "daily-summary",
    () => plannerApi.dailySummary(),
    { refreshInterval: 60_000 }
  );

  return {
    summary: data ?? null,
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

/**
 * The Today dashboard's "Start your day" lock (services/schedule_service.py).
 * Refreshes every 30s mostly so a plan started in another tab/device shows
 * up here without a manual reload — the write itself (startDay) always
 * mutates optimistically-ish by re-fetching right after the POST resolves.
 */
export function useDailyPlan() {
  const { data, error, isLoading, mutate } = useSWR(
    "daily-plan",
    () => scheduleApi.today(),
    { refreshInterval: 30_000 }
  );

  return {
    plan: data ?? null,
    isLoading,
    error,
    refresh: mutate,
    startDay: async (bufferMultiplier: number) => {
      const plan = await scheduleApi.startDay(bufferMultiplier);
      await mutate(plan);
      return plan;
    },
  };
}
