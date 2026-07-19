# Scheduler and Planning Engine — Milestone 5

Implements the back half of the planning pipeline: Time Estimation, Priority
Calculation, Schedule Optimization, and dynamic replanning. Turns
`GET /api/planner/next-task` and `POST /api/planner/replan` from `501` into
real, working endpoints.

## What's live

- **`backend/ml/estimator.py`** — `estimate_hours()` predicts a task's
  duration from the user's own history: median `actual_hours` of their
  completed tasks in the same project, falling back to the same importance
  tier (any project), falling back to a flat importance-based default for a
  brand-new install with no history yet. `ensure_estimate()` fills in
  `estimated_hours`/`confidence_score` on a task if either is missing and
  logs a `Prediction` row. `resolve_prediction()` backfills `actual_hours`/
  `error_pct` on that Prediction once a task completes.
- **`backend/ml/priority_model.py`** — `compute_priority_score()` is the
  hand-tuned weighted sum from `ARCHITECTURE.md`: Deadline Risk + Importance
  + Estimated Hours + Context Switching Cost + Energy Pattern Fit, each
  normalized to 0-1 and weighted per `backend/config.py::PRIORITY_WEIGHTS`.
  `compute_context_switch_cost()` is its own function (not folded into the
  main score) because `scheduler_service` needs to call it standalone while
  walking a sequence of tasks in schedule order.
- **`backend/services/scheduler_service.py`** — `generate_free_slots()`
  computes working-hour slots over a horizon and carves out existing
  `CalendarEvent` rows; `pack_tasks_into_schedule()` greedily assigns
  priority-ordered tasks into the earliest slot that fits, splitting
  leftover time into a new slot; `schedule_pending_tasks()` is the full
  orchestration (estimate -> prioritize -> pack) called by the morning job
  and by `replan()`; `get_next_task()` scores every active task fresh
  against right now and returns the single highest-priority one;
  `complete_task()` is the multi-step "mark done -> derive actual_hours
  from sessions -> resolve the pending Prediction" flow that used to be
  inline in `api/tasks.py` — moved here per the note left in that file
  during Milestone 3.
- **`backend/services/deadline_service.py`** — `detect_at_risk_tasks()`
  checks whether a task's remaining estimated hours can actually fit in the
  free calendar time between now and its deadline. `replan()` is the full
  sequence: detect at-risk tasks, demote the LOW/MEDIUM importance ones
  (push their deadline out — HIGH/CRITICAL tasks are left visibly at-risk
  rather than quietly rescheduled), wipe the future schedule, and repack
  everything tightest-first by priority.
- **`backend/scheduler/morning.py`** / **`nightly.py`** — real APScheduler
  job bodies now, registered in `app.py`'s `lifespan` at
  `config.MORNING_JOB_HOUR` / `config.NIGHTLY_JOB_HOUR`. Morning schedules
  pending tasks and computes the day's "Do Next" recommendation; nightly
  rolls up today's `ProductivityMetric` and runs a full `replan()`. Both
  write their summary to the `settings` table (no dashboard API exists yet
  to push it to — Milestone 7/8 reads it from there) and both are also
  runnable directly (`python -m backend.scheduler.morning`) for manual
  testing without waiting for the cron trigger.
- **`api/planner.py`** — `GET /next-task` returns `{"task": null}` rather
  than a 404 when nothing's active (an empty queue is a valid state, not an
  error). `POST /replan` returns a `ReplanResponse` summarizing what
  changed.
- **`api/tasks.py`** — `complete_task` now delegates to
  `scheduler_service.complete_task()` instead of doing the status/timestamp
  update inline.

## Design decisions

- **No real Google Calendar yet, and the scheduler doesn't need one to
  work.** `CalendarEvent` rows created here (`source=BRAIN_DUMP`) already
  double as the local calendar per the model's own docstring from
  Milestone 2. `generate_free_slots()` carves around whatever's in that
  table regardless of where it came from — so Milestone 6 wiring in real
  Google events later is a matter of that table gaining rows with
  `source=GOOGLE`, not a change to this module.
- **Estimator is statistical (group median), not a trained model.**
  `ml/estimator.py`'s docstring is explicit about why: a learned regressor
  needs a minimum viable training set this app doesn't have on day one, and
  can't degrade gracefully to "reasonable default" the way a median-with-
  fallback-ladder can. `confidence_score` reflects how far down that ladder
  the estimate had to go — this is exactly the same reasoning `ARCHITECTURE.md`
  and `ml/priority_model.py`'s docstring already gave for keeping the
  priority engine a hand-tuned weighted sum until Milestone 8.
- **`priority_score` is deliberately recomputed on every `next-task` call,
  not read from the last `schedule_pending_tasks()` batch.** A batch score
  goes stale the moment time passes (deadline risk shifts) or a task
  completes (context switch cost against "what's next" changes). The
  `/next-task` endpoint always reflects right now.
- **`replan()` never drops a task, only reschedules or demotes.** Compression
  means wiping and repacking *future, not-yet-started* CalendarEvents/
  WorkSessions — anything already in progress (`start_time <= now`) is left
  alone, so replanning mid-session doesn't erase what's currently happening.
- **Demotion is importance-gated.** Only LOW/MEDIUM tasks get their deadline
  pushed automatically. HIGH/CRITICAL tasks that are still at-risk after a
  full repack stay at-risk in the response on purpose — silently moving a
  critical deadline is exactly the kind of thing `notification_service.py`
  (later milestone) needs to surface to the user, not something this layer
  should paper over.
- **`complete_task()` derives `actual_hours` from `WorkSession.duration_minutes`
  only if the user didn't set it by hand**, and only sums sessions that
  actually have a `duration_minutes` (i.e. were actually started/stopped,
  not just scheduled). A task with only *scheduled* (never started) sessions
  correctly ends up with `actual_hours = None` — there's no real timer data
  yet, and inventing an estimate-as-actual would poison the training set
  `Prediction` rows are collecting for Milestone 8.
- **SQLite naive/aware datetime round-tripping.** `DateTime(timezone=True)`
  columns don't survive SQLite's string storage with their tzinfo intact —
  every value read back is naive. `scheduler_service._as_utc()` normalizes
  `CalendarEvent` times on the way out of `get_busy_intervals()`; the same
  naive-then-assume-UTC pattern was already used for `Task.deadline` in
  `ml/priority_model.py` and `deadline_service.py`. Worth remembering for
  any new module that reads a `DateTime(timezone=True)` column back out of
  the DB.

## Verified

Ran the full pipeline through `TestClient`: created a project and three
tasks (one critical with a near deadline, one no-project/no-deadline
one-off, one medium-importance with a distant deadline), confirmed
`GET /next-task` picked the critical task first, confirmed `POST /replan`
scheduled all three into `CalendarEvent`/`WorkSession` pairs in the correct
priority order with real free-slot packing (verified directly against
`data/tasks.db`), completed the top task and confirmed `GET /next-task`
correctly moved on to the next-highest-priority one. Separately verified
`detect_at_risk_tasks()` flags an unrealistic task (20 estimated hours, due
in an hour) as at-risk and — because it's HIGH importance — correctly does
*not* auto-demote it, leaving it in `at_risk_tasks` in the response.

## Next milestone

**Milestone 6 — Google Calendar and Todoist integrations**: implement
`backend/integrations/google_calendar.py` (OAuth flow, `get_free_busy()`,
`create_event()`) and `backend/integrations/todoist.py`
(`push_task()`/`pull_tasks()`), and turn `api/calendar.py`/`api/todoist.py`
from `501` into real sync endpoints. `scheduler_service.generate_free_slots()`
already reads busy time from the local `CalendarEvent` table, so the main
work is populating that table from the real Google Calendar API (source=
`GOOGLE`) instead of changing how the scheduler consumes it.
