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

// --- Deadline Engine (services/deadline_service.py) -------------------------

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
