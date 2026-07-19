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

export interface TodoistTask {
  todoist_id: string;
  content: string;
  due: string | null;
  priority: number;
}

export interface TodoistSyncResponse {
  pulled: number;
  pushed: number;
  closed: number;
  errors: string[];
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
