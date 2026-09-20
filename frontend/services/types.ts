/**
 * services/types.ts — mirrors backend/schemas/*.py field-for-field.
 *
 * Enum values are lowercase strings on purpose (see backend/models/enums.py
 * sa_enum() — the DB and the API both use .value, never .name). Keep these
 * in sync by hand; there are only five of them and they change rarely.
 */

export type ProjectStatus = "active" | "archived" | "completed";

export type TaskStatus =
  | "pending"
  | "in_progress"
  | "blocked"
  | "completed"
  | "cancelled";

export type Importance = "low" | "medium" | "high" | "critical";

export type EnergyLevel = "low" | "medium" | "high";

export type EventSource = "brain_dump" | "google" | "manual";

export type SyncStatus = "not_synced" | "synced" | "error";

export interface Project {
  id: number;
  name: string;
  description: string | null;
  status: ProjectStatus;
  goal_text: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreate {
  name: string;
  description?: string | null;
  goal_text?: string | null;
}

export interface ProjectUpdate {
  name?: string;
  description?: string | null;
  status?: ProjectStatus;
  goal_text?: string | null;
}

export interface Subtask {
  id: number;
  task_id: number;
  title: string;
  status: TaskStatus;
  estimated_hours: number | null;
  actual_hours: number | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface Task {
  id: number;
  project_id: number | null;
  title: string;
  description: string | null;
  status: TaskStatus;
  importance: Importance;
  energy_requirement: EnergyLevel | null;
  deadline: string | null;
  completed_at: string | null;
  // Deadline Engine outputs (PRD §19) — populated by services/deadline_service.py,
  // never client-writable (see schemas/task.py note on TaskCreate/TaskUpdate).
  recommended_deadline: string | null;
  latest_safe_start: string | null;
  risk_score: number | null;
  completion_probability: number | null;
  estimated_hours: number | null;
  actual_hours: number | null;
  confidence_score: number | null;
  priority_score: number | null;
  context_switch_cost: number | null;
  sort_order: number | null;
  created_at: string;
  updated_at: string;
  subtasks: Subtask[];
}

export interface TaskCreate {
  project_id?: number | null;
  title: string;
  description?: string | null;
  importance?: Importance;
  energy_requirement?: EnergyLevel | null;
  deadline?: string | null;
  estimated_hours?: number | null;
}

export interface TaskUpdate {
  project_id?: number | null;
  title?: string;
  description?: string | null;
  status?: TaskStatus;
  importance?: Importance;
  energy_requirement?: EnergyLevel | null;
  deadline?: string | null;
  estimated_hours?: number | null;
  actual_hours?: number | null;
  sort_order?: number | null;
}

export interface BrainDumpResponse {
  projects: Project[];
  tasks: Task[];
}

export interface GoalResponse {
  project: Project;
  tasks: Task[];
}

export interface NextTaskResponse {
  task: Task | null;
}

export interface ReplanResponse {
  rescheduled_count: number;
  rescheduled_tasks: Task[];
  demoted_tasks: Task[];
  at_risk_tasks: Task[];
}

/**
 * Dashboard hero payload (PRD §37) — a read of the last morning job's
 * cached output. All fields are null/empty-safe for a brand-new install
 * that hasn't had a morning run yet.
 */
export interface DailySummaryResponse {
  generated_at: string | null;
  scheduled_count: number;
  next_task_id: number | null;
  next_task_title: string | null;
  narration: string | null;
  narration_ai_generated: boolean;
  notifications: Record<string, unknown>[];
}

export interface CalendarEvent {
  id: number;
  task_id: number | null;
  google_event_id: string | null;
  title: string;
  start_time: string;
  end_time: string;
  source: EventSource;
  sync_status: SyncStatus;
  synced: boolean;
  created_at: string;
  updated_at: string;
}

export interface CalendarSyncResponse {
  pulled: number;
  pushed: number;
  removed: number;
  errors: string[];
}

/** GET /api/calendar/google/status — the *caller's* connection, not the server's alone. */
export interface GoogleCalendarStatus {
  oauth_client_configured: boolean;
  connected: boolean;
}

export interface GoogleConnectResponse {
  authorization_url: string;
}

// --- Deadline Engine (services/deadline_service.py) -------------------------

// Mirrors backend/schemas/schedule.BUFFER_MULTIPLIERS
export const BUFFER_MULTIPLIERS = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75] as const;

// Mirrors backend/schemas/schedule.DailyPlanRead
export interface DailyPlan {
  plan_date: string;
  buffer_multiplier: number;
  started_at: string | null;
  locked: boolean;
}

export type BufferLevel = "safe" | "default" | "aggressive";
export type BufferStatus = "done" | "safe" | "tight" | "impossible";

export interface DeadlineBuffer {
  level: BufferLevel;
  target_date: string;
  days_remaining: number;
  free_hours_available: number;
  hours_needed: number;
  suggested_daily_hours: number | null;
  status: BufferStatus;
  message: string;
}

export interface TaskDeadlinePlan {
  task_id: number;
  title: string;
  deadline: string;
  estimated_hours: number | null;
  hours_remaining: number;
  buffers: DeadlineBuffer[];
}

export type WorkloadLevel = "light" | "moderate" | "full" | "overloaded";

export interface WorkloadDay {
  date: string;
  weekday: string;
  capacity_hours: number;
  allocated_hours: number;
  utilization_pct: number;
  level: WorkloadLevel;
}

export interface WorkloadPeriod {
  label: string;
  capacity_hours: number;
  allocated_hours: number;
  utilization_pct: number;
  overload_pct: number | null;
}

export interface WorkloadResponse {
  days: WorkloadDay[];
  week: WorkloadPeriod;
  month: WorkloadPeriod;
  peak_day: string | null;
}

// --- Analytics (Milestone 8 — real, see services/analytics_service.py) -----

export interface ProjectProgress {
  project_id: number;
  project_name: string;
  tasks_total: number;
  tasks_completed: number;
  completion_rate: number;
}

export interface WeeklyReviewResponse {
  period_start: string;
  period_end: string;
  tasks_completed: number;
  tasks_planned: number;
  completion_rate: number | null;
  hours_worked: number;
  most_productive_day: string | null;
  least_productive_day: string | null;
  most_underestimated_category: string | null;
  most_underestimated_pct: number | null;
  missed_deadlines: number;
  project_progress: ProjectProgress[];
  recommendation: string;
  ai_generated: boolean;
}

export type EstimationBias = "overestimates" | "underestimates" | "accurate";

export interface CategoryEstimationError {
  category: string;
  sample_count: number;
  average_error_pct: number;
  bias: EstimationBias;
}

export interface EstimationErrorResponse {
  overall_average_error_pct: number | null;
  overall_sample_count: number;
  by_category: CategoryEstimationError[];
}

export interface EstimationErrorTrendPoint {
  date: string; // "YYYY-MM-DD"
  average_error_pct: number;
}

export interface EstimationErrorTrendResponse {
  points: EstimationErrorTrendPoint[];
}

export interface StreaksResponse {
  current_streak_days: number;
  longest_streak_days: number;
  active_today: boolean;
  last_active_date: string | null;
}

export interface HourBucket {
  hour: number;
  hours_logged: number;
  sessions_count: number;
}

export interface ProductivityHoursResponse {
  by_hour: HourBucket[];
  best_hour: number | null;
  lookback_days: number;
}

// --- Execution Score (services/execution_score_service.py, PRD §15/§37) ---

export type ExecutionScoreBand = "excellent" | "healthy" | "busy" | "high_risk" | "impossible";

export interface ExecutionScoreComponent {
  name: string;
  score: number;
  weight: number;
  detail: string;
}

export interface ExecutionScoreResponse {
  score: number;
  band: ExecutionScoreBand;
  headline: string;
  components: ExecutionScoreComponent[];
}

export interface ExecutionScoreTrendPoint {
  date: string; // "YYYY-MM-DD"
  score: number;
  band: ExecutionScoreBand;
}

export interface ExecutionScoreTrendResponse {
  points: ExecutionScoreTrendPoint[];
}

// --- AI Memory Architecture (backend/api/memory.py, PRD §63) ---------------

export type EpisodicEventType =
  | "weekly_review"
  | "project_completed"
  | "milestone"
  | "planning_decision";

export interface EpisodicEvent {
  id: number;
  event_type: EpisodicEventType;
  occurred_on: string; // "YYYY-MM-DD"
  title: string;
  summary: string;
}

export interface EpisodicMemoryResponse {
  events: EpisodicEvent[];
}

export interface EstimationAccuracySummary {
  overall_average_error_pct: number | null;
  sample_count: number;
  most_biased_category: string | null;
  most_biased_direction: EstimationBias | null;
}

export interface LongTermProfileResponse {
  generated_at: string | null;
  preferred_work_hours: number[];
  estimation_accuracy: EstimationAccuracySummary;
  recent_completed_projects: string[];
  longest_streak_days: number;
}

export type SemanticRelationType = "project_template" | "recurring_workflow";

export interface SemanticRelation {
  id: number;
  relation_type: SemanticRelationType;
  title: string;
  summary: string;
  subject_project_id: number | null;
  object_project_id: number | null;
}

export interface SemanticMemoryResponse {
  relations: SemanticRelation[];
}

// --- AI Execution Coach (services/ai_coach_service.py, PRD §24) ------------

export interface ChatResponse {
  agent: string;
  message: string;
  data: Record<string, unknown> | null;
}

// --- Notification System (services/notification_service.py, PRD §27) -----

export type NotificationSeverity = "info" | "warning" | "critical";

export interface NotificationItem {
  type: string;
  severity: NotificationSeverity;
  message: string;
  task_id: number | null;
  action: string | null;
}

export interface NotificationsResponse {
  notifications: NotificationItem[];
}

// --- Settings (backend/api/settings.py) -------------------------------------

export interface UserSettings {
  display_name: string;
  email: string;
  dark_mode: boolean;
  weekday_start_hour: number;
  weekday_end_hour: number;
  weekend_start_hour: number;
  weekend_end_hour: number;
}

export type UserSettingsUpdate = Partial<UserSettings>;

export type TimeBlockCategory = "meal" | "class" | "gym" | "other";

export interface TimeBlockCreate {
  label: string;
  category: TimeBlockCategory;
  /** "HH:MM", 24-hour, local wall-clock time. */
  start_time: string;
  end_time: string;
  /** 0=Monday .. 6=Sunday. */
  days_of_week: number[];
}

export interface TimeBlock extends TimeBlockCreate {
  id: string;
}

// --- Explainability layer (backend/services/explanation_service.py) ---------

/** Raw 0-1 inputs behind priority_score, before weighting. Note
 * `context_switch_cost` is a *cost* — lower is better, unlike the rest. */
export interface PriorityComponents {
  deadline_risk: number;
  importance: number;
  estimated_hours: number;
  context_switch_cost: number;
  energy_fit: number;
}

export interface NextTaskExplanation {
  task_id: number;
  title: string;
  priority_score: number | null;
  components: PriorityComponents;
  unlocks_task_count: number;
  reasons: string[];
}

export interface NextTaskExplanationResponse {
  explanation: NextTaskExplanation | null;
}

export type EstimateBaseTier =
  | "project_history"
  | "trained_model"
  | "importance_history"
  | "default";

export interface EstimateExplanation {
  task_id: number;
  title: string;
  base_hours: number;
  base_tier: EstimateBaseTier;
  confidence: number;
  category: string;
  calibration_bias_pct: number | null;
  calibration_sample_count: number;
  calibration_applied_pct: number;
  calibrated_hours: number;
  reasons: string[];
}

export interface DeadlineRiskExplanation {
  task_id: number;
  title: string;
  plan: TaskDeadlinePlan;
  reasons: string[];
}

export interface ScheduleChangeExplanation {
  occurred_on: string;
  summary: string;
  reasons: string[];
}

export interface ScheduleChangeExplanationResponse {
  explanation: ScheduleChangeExplanation | null;
}

/** One category ml/calibration.py is actively applying to new estimates.
 * `bias_pct` > 0 means actual work ran longer than predicted. */
export interface CalibrationCategory {
  category: string;
  bias_pct: number;
  sample_count: number;
  confidence: number;
}

export interface CalibrationResponse {
  categories: CalibrationCategory[];
}

// --- Demo workspace (backend/api/demo.py) ------------------------------------

export interface DemoSeedResponse {
  projects_created: number;
  tasks_completed: number;
  tasks_pending: number;
  sessions_created: number;
  predictions_created: number;
  metrics_days: number;
  /** True when a demo workspace already existed and nothing was created. */
  already_seeded: boolean;
}

export interface DemoResetResponse {
  projects_removed: number;
  metrics_removed: number;
}

/** Thrown by services/api.ts for any non-2xx response. */
export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

// --- Auth ---------------------------------------------------------------

export interface AuthUser {
  id: number;
  email: string;
  name?: string | null;
  google_picture_url?: string | null;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: AuthUser;
}