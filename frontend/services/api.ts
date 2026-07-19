/**
 * services/api.ts — thin typed client over the Milestones 1-6 FastAPI
 * backend. One function per route in backend/api/API.md. No SDK, no
 * codegen: the API surface is small and stable enough that hand-written
 * types (services/types.ts) are less overhead than a generator.
 *
 * Every route this file calls is real (200) except the four analytics
 * routes, which are documented 501s until Milestone 8 — analyticsApi
 * below throws ApiError(501) and callers render an empty state, not a
 * crash.
 */

import {
  ApiError,
  BrainDumpResponse,
  CalendarEvent,
  CalendarSyncResponse,
  GoalResponse,
  NextTaskResponse,
  Project,
  ProjectCreate,
  ProjectUpdate,
  ReplanResponse,
  Subtask,
  Task,
  TaskCreate,
  TaskUpdate,
  TodoistSyncResponse,
  TodoistTask,
} from "./types";

const BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options.headers,
      },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      0,
      "Can't reach the Brain Dump backend. Is `uvicorn app:app` running on " +
        BASE_URL +
        "?"
    );
  }

  if (res.status === 204) {
    return undefined as T;
  }

  const isJson = res.headers.get("content-type")?.includes("application/json");
  const body = isJson ? await res.json().catch(() => null) : null;

  if (!res.ok) {
    const message =
      (body && typeof body === "object" && "detail" in body && String(body.detail)) ||
      `${res.status} ${res.statusText}`;
    throw new ApiError(res.status, message, body);
  }

  return body as T;
}

const get = <T>(path: string) => request<T>(path, { method: "GET" });
const post = <T>(path: string, data?: unknown) =>
  request<T>(path, { method: "POST", body: data ? JSON.stringify(data) : undefined });
const put = <T>(path: string, data: unknown) =>
  request<T>(path, { method: "PUT", body: JSON.stringify(data) });
const del = <T>(path: string) => request<T>(path, { method: "DELETE" });

// --- Health ---------------------------------------------------------------

export const healthApi = {
  check: () => get<{ status: string }>("/health"),
};

// --- Projects ---------------------------------------------------------------

export const projectsApi = {
  list: (statusFilter?: string) =>
    get<Project[]>(`/api/projects/${statusFilter ? `?status_filter=${statusFilter}` : ""}`),
  get: (id: number) => get<Project>(`/api/projects/${id}`),
  create: (data: ProjectCreate) => post<Project>("/api/projects/", data),
  update: (id: number, data: ProjectUpdate) => put<Project>(`/api/projects/${id}`, data),
  remove: (id: number) => del<void>(`/api/projects/${id}`),
};

// --- Tasks ---------------------------------------------------------------

export const tasksApi = {
  list: (params?: { projectId?: number; statusFilter?: string }) => {
    const qs = new URLSearchParams();
    if (params?.projectId != null) qs.set("project_id", String(params.projectId));
    if (params?.statusFilter) qs.set("status_filter", params.statusFilter);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return get<Task[]>(`/api/tasks/${suffix}`);
  },
  get: (id: number) => get<Task>(`/api/tasks/${id}`),
  create: (data: TaskCreate) => post<Task>("/api/tasks/", data),
  update: (id: number, data: TaskUpdate) => put<Task>(`/api/tasks/${id}`, data),
  remove: (id: number) => del<void>(`/api/tasks/${id}`),
  complete: (id: number) => post<Task>(`/api/tasks/${id}/complete`),
  addSubtask: (taskId: number, data: { title: string; estimated_hours?: number | null }) =>
    post<Subtask>(`/api/tasks/${taskId}/subtasks`, data),
  listSubtasks: (taskId: number) => get<Subtask[]>(`/api/tasks/${taskId}/subtasks`),
  updateSubtask: (
    id: number,
    data: Partial<Pick<Subtask, "title" | "status" | "estimated_hours" | "actual_hours">>
  ) => put<Subtask>(`/api/tasks/subtasks/${id}`, data),
  removeSubtask: (id: number) => del<void>(`/api/tasks/subtasks/${id}`),
};

// --- Planner (AI agents + scheduler) ---------------------------------------

export const plannerApi = {
  brainDump: (text: string) =>
    post<BrainDumpResponse>("/api/planner/brain-dump", { text }),
  goal: (goalText: string) =>
    post<GoalResponse>("/api/planner/goal", { goal_text: goalText }),
  nextTask: () => get<NextTaskResponse>("/api/planner/next-task"),
  replan: () => post<ReplanResponse>("/api/planner/replan"),
};

// --- Calendar (Milestone 6) --------------------------------------------------

export const calendarApi = {
  events: (source?: string) =>
    get<CalendarEvent[]>(`/api/calendar/events${source ? `?source=${source}` : ""}`),
  sync: () => post<CalendarSyncResponse>("/api/calendar/sync"),
  createSession: (data: { task_id: number; start_time: string; end_time: string }) =>
    post<CalendarEvent>("/api/calendar/create-session", data),
};

// --- Todoist (Milestone 6) ---------------------------------------------------

export const todoistApi = {
  tasks: () => get<TodoistTask[]>("/api/todoist/tasks"),
  sync: () => post<TodoistSyncResponse>("/api/todoist/sync"),
  pushTask: (taskId: number) =>
    post<{ task_id: number; todoist_id: string }>("/api/todoist/push-task", {
      task_id: taskId,
    }),
};

// --- Analytics (Milestone 8 — currently 501) --------------------------------
// Kept as real calls (not stubs) so the moment Milestone 8 lands these
// start returning data with zero frontend changes. Callers should catch
// ApiError with status 501 and render EmptyState, not treat it as a bug.

export const analyticsApi = {
  weeklyReview: () => get<unknown>("/api/analytics/weekly-review"),
  estimationError: () => get<unknown>("/api/analytics/estimation-error"),
  streaks: () => get<unknown>("/api/analytics/streaks"),
  productivityHours: () => get<unknown>("/api/analytics/productivity-hours"),
};

export { ApiError, BASE_URL };
