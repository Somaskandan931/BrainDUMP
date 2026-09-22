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
  ActivityEntry,
  ActivityFeedResponse,
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
// The short-lived access token lives in localStorage and is attached as a
// Bearer header (below); there's still no server-rendered authenticated page
// that needs it available server-side. The long-lived session itself now
// lives in an HttpOnly refresh-token cookie the browser holds automatically
// (see _set_refresh_cookie in backend/api/auth.py) -- localStorage never
// sees that token, which is the point: it can't be read by JS/XSS, only
// exchanged via POST /api/auth/refresh (see refreshAccessToken below).
// lib/auth.tsx is the only other place that reads/writes the TOKEN_KEY.
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

// --- Silent refresh-on-401 ---------------------------------------------------
// The backend now also sets an HttpOnly refresh-token cookie on every login
// path (see backend/api/auth.py's _issue_session). `credentials: "include"`
// below is what makes the browser actually send/accept that cookie against
// BASE_URL. A bare token expiry (access tokens are short-lived,
// config.ACCESS_TOKEN_EXPIRE_MINUTES) shouldn't drop the user back to
// /login: we get exactly one shot at POST /api/auth/refresh to mint a new
// access token from the cookie, then retry the original request once. Only
// if that refresh itself fails (cookie missing/expired/reused) do we treat
// it as a real sign-out via clearToken(). Concurrent 401s share one
// in-flight refresh instead of each firing their own POST /refresh.
let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  if (refreshPromise) return refreshPromise;
  refreshPromise = (async () => {
    try {
      const res = await fetch(`${BASE_URL}/api/auth/refresh`, {
        method: "POST",
        credentials: "include",
        cache: "no-store",
      });
      if (!res.ok) return null;
      const body = (await res.json().catch(() => null)) as AuthResponse | null;
      if (!body?.access_token) return null;
      setToken(body.access_token);
      return body.access_token;
    } catch {
      return null;
    } finally {
      refreshPromise = null;
    }
  })();
  return refreshPromise;
}

const AUTH_ROUTES = new Set(["/api/auth/login", "/api/auth/register", "/api/auth/refresh"]);

async function request<T>(
  path: string,
  options: RequestInit = {},
  _isRetry = false
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
      credentials: "include",
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

  if (res.status === 401 && !_isRetry && !AUTH_ROUTES.has(path)) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      return request<T>(path, options, true);
    }
    clearToken();
  } else if (res.status === 401 && AUTH_ROUTES.has(path) && path !== "/api/auth/login" && path !== "/api/auth/register") {
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
  // Mints a new access token from the HttpOnly refresh cookie. request()
  // above already calls this internally on a 401; exposed here mainly for
  // an explicit "restore session on app load" call from lib/auth.tsx.
  refresh: () => post<AuthResponse>("/api/auth/refresh"),
  // Revokes the refresh session server-side and clears the cookie. Safe to
  // call even with no session (backend no-ops rather than 401ing).
  logout: () => request<void>("/api/auth/logout", { method: "POST" }),
  confirmEmail: (token: string) =>
    post<AuthUser>("/api/auth/verify-email/confirm", { token }),
  requestPasswordReset: (email: string) =>
    post<{ message: string }>("/api/auth/password-reset/request", { email }),
  confirmPasswordReset: (token: string, newPassword: string) =>
    request<void>("/api/auth/password-reset/confirm", {
      method: "POST",
      body: JSON.stringify({ token, new_password: newPassword }),
    }),
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
  // Full audit trail for one task (create/update/complete/skip/archive/
  // deadline-pushed), newest first. Backed by activity_service.get_entity_history.
  history: (id: number) => get<ActivityEntry[]>(`/api/tasks/${id}/history`),
};

// --- Activity (account-wide audit feed, backend/api/v1/activity.py) --------

export const activityApi = {
  list: (params?: {
    entityType?: string;
    entityId?: number;
    action?: string;
    cursor?: number;
    limit?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.entityType) qs.set("entity_type", params.entityType);
    if (params?.entityId != null) qs.set("entity_id", String(params.entityId));
    if (params?.action) qs.set("action", params.action);
    if (params?.cursor != null) qs.set("cursor", String(params.cursor));
    if (params?.limit != null) qs.set("limit", String(params.limit));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return get<ActivityFeedResponse>(`/api/activity/${suffix}`);
  },
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

export { ApiError, BASE_URL };