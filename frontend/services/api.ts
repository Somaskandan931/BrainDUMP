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
  ActivityItem,
  ActivityPage,
  ApiError,
  AuthResponse,
  AuthUser,
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
  GoogleCalendarStatus,
  GoogleConnectResponse,
  LongTermProfileResponse,
  MessageResponse,
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

// --- Auth token storage -----------------------------------------------------
// A plain localStorage string, not a cookie: this is a local-first app with
// no server-rendered authenticated pages, so there's nothing that needs the
// token available server-side. lib/auth.tsx is the only other place that
// reads/writes this key directly.
const TOKEN_KEY = "brain_dump_token";
const AUTH_EVENT = "brain-dump-auth-cleared";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
  // lib/auth.tsx listens for this so a 401 anywhere (not just from an
  // explicit logout click) immediately drops the user back to /login.
  window.dispatchEvent(new Event(AUTH_EVENT));
}

export function onAuthCleared(handler: () => void): () => void {
  window.addEventListener(AUTH_EVENT, handler);
  return () => window.removeEventListener(AUTH_EVENT, handler);
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
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

  if (res.status === 401 && path !== "/api/auth/login" && path !== "/api/auth/register") {
    clearToken();
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

// --- Auth ---------------------------------------------------------------

export const authApi = {
  register: (data: { email: string; password: string; name?: string }) =>
    post<AuthResponse>("/api/auth/register", data),
  login: (data: { email: string; password: string }) =>
    post<AuthResponse>("/api/auth/login", data),
  loginWithGoogle: (idToken: string) =>
    post<AuthResponse>("/api/auth/google", { id_token: idToken }),
  loginWithGithub: (code: string) =>
    post<AuthResponse>("/api/auth/github", { code }),
  me: () => get<AuthUser>("/api/auth/me"),
  resendVerificationEmail: (email: string) =>
    post<MessageResponse>("/api/auth/verify-email/resend", { email }),
  confirmEmail: (token: string) =>
    post<MessageResponse>("/api/auth/verify-email/confirm", { token }),
  requestPasswordReset: (email: string) =>
    post<MessageResponse>("/api/auth/password-reset/request", { email }),
  confirmPasswordReset: (token: string, newPassword: string) =>
    post<MessageResponse>("/api/auth/password-reset/confirm", { token, new_password: newPassword }),
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
  // "What happened to this task, and why?" -- newest first (activity_service.py).
  // Includes any deadline the planner moved, with the recorded reason.
  history: (id: number, limit = 100) =>
    get<ActivityItem[]>(`/api/tasks/${id}/history?limit=${limit}`),
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
  // Per-user Google connection (backend/api/calendar.py). `googleConnect` is a
  // fetch with the bearer token rather than a plain link, because the browser
  // can't attach an Authorization header to a navigation; the caller then sends
  // the browser to the returned URL.
  googleStatus: () => get<GoogleCalendarStatus>("/api/calendar/google/status"),
  googleConnect: () => get<GoogleConnectResponse>("/api/calendar/google/connect"),
  googleDisconnect: () => del<void>("/api/calendar/google"),
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

// --- Activity / audit trail (backend/api/v1/activity.py) --------------------
// Read-only by design: the server writes these rows itself when something
// happens, so there is no create/update/delete here.

export const activityApi = {
  list: (params?: {
    entityType?: string;
    entityId?: number;
    action?: string;
    limit?: number;
    beforeId?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.entityType) qs.set("entity_type", params.entityType);
    if (params?.entityId != null) qs.set("entity_id", String(params.entityId));
    if (params?.action) qs.set("action", params.action);
    if (params?.limit != null) qs.set("limit", String(params.limit));
    if (params?.beforeId != null) qs.set("before_id", String(params.beforeId));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return get<ActivityPage>(`/api/activity/${suffix}`);
  },
};

export { ApiError, BASE_URL };