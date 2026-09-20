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
  CalibrationResponse,
  ChatResponse,
  DailyPlan,
  DailySummaryResponse,
  DeadlineRiskExplanation,
  DemoResetResponse,
  DemoSeedResponse,
  EpisodicMemoryResponse,
  EstimateExplanation,
  EstimationErrorResponse,
  EstimationErrorTrendResponse,
  ExecutionScoreResponse,
  ExecutionScoreTrendResponse,
  GoalResponse,
  LongTermProfileResponse,
  NextTaskExplanationResponse,
  NextTaskResponse,
  NotificationsResponse,
  ProductivityHoursResponse,
  Project,
  ProjectCreate,
  ProjectUpdate,
  ReplanResponse,
  ScheduleChangeExplanationResponse,
  SemanticMemoryResponse,
  StreaksResponse,
  Subtask,
  Task,
  TaskCreate,
  TaskDeadlinePlan,
  TaskUpdate,
  TimeBlock,
  TimeBlockCreate,
  UserSettings,
  UserSettingsUpdate,
  WeeklyReviewResponse,
  WorkloadResponse,
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
  skip: (id: number) => post<Task>(`/api/tasks/${id}/skip`),
  reorder: (taskIds: number[]) => post<Task[]>("/api/tasks/reorder", { task_ids: taskIds }),
  addSubtask: (taskId: number, data: { title: string; estimated_hours?: number | null }) =>
    post<Subtask>(`/api/tasks/${taskId}/subtasks`, data),
  listSubtasks: (taskId: number) => get<Subtask[]>(`/api/tasks/${taskId}/subtasks`),
  updateSubtask: (
    id: number,
    data: Partial<Pick<Subtask, "title" | "status" | "estimated_hours" | "actual_hours">>
  ) => put<Subtask>(`/api/tasks/subtasks/${id}`, data),
  removeSubtask: (id: number) => del<void>(`/api/tasks/subtasks/${id}`),
  deadlinePlan: (id: number) => get<TaskDeadlinePlan>(`/api/tasks/${id}/deadline-plan`),
  // "Why this estimate?" / "Why is this deadline at risk?" (explanation_service.py).
  // explainDeadlineRisk 400s for a task with no deadline, same as deadlinePlan.
  explainEstimate: (id: number) => get<EstimateExplanation>(`/api/tasks/${id}/explain-estimate`),
  explainDeadlineRisk: (id: number) =>
    get<DeadlineRiskExplanation>(`/api/tasks/${id}/explain-deadline-risk`),
};

// --- Planner (AI agents + scheduler) ---------------------------------------

export const plannerApi = {
  brainDump: (text: string) =>
    post<BrainDumpResponse>("/api/planner/brain-dump", { text }),
  goal: (goalText: string) =>
    post<GoalResponse>("/api/planner/goal", { goal_text: goalText }),
  nextTask: () => get<NextTaskResponse>("/api/planner/next-task"),
  replan: () => post<ReplanResponse>("/api/planner/replan"),
  dailySummary: () => get<DailySummaryResponse>("/api/planner/today"),
  // "Why this task?" / "Why did my schedule change?" — both return
  // {"explanation": null} for the empty case rather than a 404.
  explainNextTask: () => get<NextTaskExplanationResponse>("/api/planner/next-task/explain"),
  explainReplan: () => get<ScheduleChangeExplanationResponse>("/api/planner/replan/explain"),
};

// --- Calendar (Milestone 6) --------------------------------------------------

export const calendarApi = {
  events: (source?: string) =>
    get<CalendarEvent[]>(`/api/calendar/events${source ? `?source=${source}` : ""}`),
  sync: () => post<CalendarSyncResponse>("/api/calendar/sync"),
  createSession: (data: { task_id: number; start_time: string; end_time: string }) =>
    post<CalendarEvent>("/api/calendar/create-session", data),
};

// --- Schedule (Today dashboard "Start your day" lock, backend/api/schedule.py) -

export const scheduleApi = {
  today: () => get<DailyPlan>("/api/schedule/today"),
  startDay: (bufferMultiplier: number) =>
    post<DailyPlan>("/api/schedule/start-day", { buffer_multiplier: bufferMultiplier }),
};

// --- Analytics (Milestone 8 — real, backed by services/analytics_service.py) -

export const analyticsApi = {
  weeklyReview: () => get<WeeklyReviewResponse>("/api/analytics/weekly-review"),
  estimationError: () => get<EstimationErrorResponse>("/api/analytics/estimation-error"),
  estimationErrorTrend: () => get<EstimationErrorTrendResponse>("/api/analytics/estimation-error/trend"),
  streaks: () => get<StreaksResponse>("/api/analytics/streaks"),
  productivityHours: () => get<ProductivityHoursResponse>("/api/analytics/productivity-hours"),
  // Workload Engine (PRD Milestone 4) — daily/weekly/monthly capacity vs.
  // allocated hours, backed by services/workload_service.py.
  workload: () => get<WorkloadResponse>("/api/analytics/workload"),
  // Execution Score (PRD §15/§37, Algorithm 8) — the dashboard hero metric.
  executionScore: () => get<ExecutionScoreResponse>("/api/analytics/execution-score"),
  // Execution Score trend — one point per day, nightly-job snapshots plus
  // a live-computed point for today (see execution_score_service.get_execution_score_trend).
  executionScoreTrend: () => get<ExecutionScoreTrendResponse>("/api/analytics/execution-score/trend"),
  // Personal Calibration (ml/calibration.py) — the per-category bias currently
  // being applied to new estimates.
  calibration: () => get<CalibrationResponse>("/api/analytics/calibration"),
};

// --- Demo workspace (backend/api/demo.py) ----------------------------------

export const demoApi = {
  seed: () => post<DemoSeedResponse>("/api/demo/seed"),
  reset: () => post<DemoResetResponse>("/api/demo/reset"),
};

// --- AI Memory Architecture (backend/api/memory.py, PRD §63) ---------------

export const memoryApi = {
  episodic: (limit = 10) => get<EpisodicMemoryResponse>(`/api/memory/episodic?limit=${limit}`),
  longTerm: () => get<LongTermProfileResponse>("/api/memory/long-term"),
  semantic: (limit = 10) => get<SemanticMemoryResponse>(`/api/memory/semantic?limit=${limit}`),
};

// --- AI Execution Coach (services/ai_coach_service.py) ---------------------

export const chatApi = {
  send: (message: string) => post<ChatResponse>("/api/chat/", { message }),
};

// --- Notifications (services/notification_service.py) ----------------------

export const notificationsApi = {
  list: () => get<NotificationsResponse>("/api/notifications/"),
};

// --- Settings (backend/api/settings.py) -------------------------------------

export const settingsApi = {
  get: () => get<UserSettings>("/api/settings"),
  update: (data: UserSettingsUpdate) => put<UserSettings>("/api/settings", data),
  timeBlocks: () => get<TimeBlock[]>("/api/settings/time-blocks"),
  createTimeBlock: (data: TimeBlockCreate) => post<TimeBlock>("/api/settings/time-blocks", data),
  removeTimeBlock: (id: string) => del<void>(`/api/settings/time-blocks/${id}`),
};

export { ApiError, BASE_URL };