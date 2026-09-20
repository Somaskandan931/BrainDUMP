# Scheduler and Planning Engine

Implements the back half of the planning pipeline: Time Estimation, Priority
Calculation, Schedule Optimization, and dynamic replanning, backing
`GET /api/planner/next-task` and `POST /api/planner/replan`.

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
  leftover time into a new slot; `_cluster_similar_tasks()` (Rule 9:
  "Group similar work together") reorders that priority-ordered list so
  same-project tasks whose priority scores are within
  `config.CLUSTER_PRIORITY_TOLERANCE` of each other land adjacent,
  instead of interleaved in whatever order they happened to score in —
  see "Design decisions" below for why project_id is the grouping key;
  `schedule_pending_tasks()` is the full orchestration (estimate ->
  prioritize -> cluster -> pack) called by the morning job and by
  `replan()`; `get_next_task()` scores every active task fresh against
  right now and returns the single highest-priority one; `complete_task()`
  is the multi-step "mark done -> derive actual_hours from sessions ->
  resolve the pending Prediction -> check for a milestone" flow, moved
  here from `api/tasks.py` to keep routes thin.
- **`backend/ai/long_term_memory.py`** — `derived_energy_pattern()` feeds
  learned `preferred_work_hours` back into the scheduler: both
  `schedule_pending_tasks()` and `get_next_task()` resolve it via
  `scheduler_service._resolve_energy_pattern()` and pass it through to
  `compute_priority_score()`/`energy_fit_at_hour()` in place of
  `config.DEFAULT_ENERGY_PATTERN`'s static curve, once there's enough
  logged `WorkSession` history behind it to trust (see that function's
  own sample-size guard). Below that bar, scheduling is unaffected — the
  profile stays advisory-only exactly as before this was wired up.
- **`backend/services/deadline_service.py`** — `detect_at_risk_tasks()`
  checks whether a task's remaining estimated hours can actually fit in the
  free calendar time between now and its deadline. `replan()` is the full
  sequence: detect at-risk tasks, demote the LOW/MEDIUM importance ones
  (push their deadline out — HIGH/CRITICAL tasks are left visibly at-risk
  rather than quietly rescheduled), wipe the future schedule, and repack
  everything tightest-first by priority.
- **`backend/scheduler/morning.py`** / **`nightly.py`** — real APScheduler
  job bodies, registered in `app.py`'s `lifespan` at
  `config.MORNING_JOB_HOUR` / `config.NIGHTLY_JOB_HOUR`. Morning schedules
  pending tasks and computes the day's "Do Next" recommendation; nightly
  rolls up today's `ProductivityMetric` and runs a full `replan()`. Both
  write their summary to the `settings` table (the frontend dashboard reads
  it from there) and both are also runnable directly
  (`python -m backend.scheduler.morning`) for manual testing without
  waiting for the cron trigger.
- **`api/planner.py`** — `GET /next-task` returns `{"task": null}` rather
  than a 404 when nothing's active (an empty queue is a valid state, not an
  error). `POST /replan` returns a `ReplanResponse` summarizing what
  changed.
- **`api/tasks.py`** — `complete_task` now delegates to
  `scheduler_service.complete_task()` instead of doing the status/timestamp
  update inline.

## Design decisions

- **No real Google Calendar dependency — the scheduler doesn't need one
  to work.** `CalendarEvent` rows created here (`source=BRAIN_DUMP`)
  already double as the local calendar per the model's own docstring.
  `generate_free_slots()` carves around whatever's in that table
  regardless of where it came from — so wiring in real Google events
  later (see `INTEGRATIONS.md`) is a matter of that table gaining rows
  with `source=GOOGLE`, not a change to this module.
- **Estimator is statistical (group median), not a trained model.**
  `ml/estimator.py`'s docstring is explicit about why: a learned regressor
  needs a minimum viable training set this app doesn't have on day one, and
  can't degrade gracefully to "reasonable default" the way a median-with-
  fallback-ladder can. `confidence_score` reflects how far down that ladder
  the estimate had to go — this is exactly the same reasoning `ARCHITECTURE.md`
  and `ml/priority_model.py`'s docstring already gave for keeping the
  priority engine a hand-tuned weighted sum (see `ANALYTICS.md` for why a
  learned version still isn't a good fit).
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
  (not yet built) needs to surface to the user, not something this layer
  should paper over.
- **`complete_task()` derives `actual_hours` from `WorkSession.duration_minutes`
  only if the user didn't set it by hand**, and only sums sessions that
  actually have a `duration_minutes` (i.e. were actually started/stopped,
  not just scheduled). A task with only *scheduled* (never started) sessions
  correctly ends up with `actual_hours = None` — there's no real timer data
  yet, and inventing an estimate-as-actual would poison the training set
  `Prediction` rows are collecting for future estimator training (see
  `ANALYTICS.md`).
- **Rule 9 clustering groups by `project_id`, not a task category/label.**
  `models/task.py` has no labels or category field (the same gap
  `ai/long_term_memory.py` documents for why "frequently used labels"
  was dropped from the Long-Term Memory profile) — so `project_id` is
  the only real "kind of work" signal available, the same one Rule 10 /
  `compute_context_switch_cost()` already uses. `_cluster_similar_tasks()`
  only reorders within priority ties (`config.CLUSTER_PRIORITY_TOLERANCE`
  wide) — it never lets "group similar work" push a genuinely
  higher-priority task from a different project further down the day.
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

Separately (once this sandbox had `sqlalchemy`/`ollama`/`apscheduler`
installed, so this ran against a real SQLite engine rather than only
`py_compile`): `_cluster_similar_tasks()` reproduces the PRD's own worked
example directly (`Coding, Email, Coding, Reading, Coding` ->
`Coding, Coding, Coding, Email, Reading`), confirmed a genuinely
higher-priority different-project task is never displaced across a tie
band boundary, and confirmed `None`-project tasks bucket together too.
End-to-end: created 5 tasks interleaved across 2 real `Project` rows with
near-equal priority and ran the actual `schedule_pending_tasks()` against
an in-memory DB — the same-project tasks came out contiguous in the real
returned schedule order, not just in the intermediate list.

Separately re-ran both of the above against a fresh in-memory SQLite engine
end to end (previously only `py_compile`-checked, no dependencies
installed): completing all 4 tasks of a real `Project` produced exactly
the 25/50/75/100% `EpisodicMemory` rows in order; `derived_energy_pattern()`
correctly returned `None` under the 10-session sample-size bar and, above
it, produced the expected high/medium/low curve around the learned peak
hour. Also hit `GET /api/planner/today` through a real `TestClient`: on an
empty `settings` table it returns the all-null/zero default response
(200, not 404/500) exactly as designed; after seeding a `last_morning_summary`
row shaped like `scheduler/morning.py`'s real output — including extra keys
(`scheduled_task_ids`, `calendar_sync`) that aren't part of the response
schema — the endpoint correctly ignores the extras and returns the
narration/next-task fields untouched, confirming the frontend's
`useDailySummary()` hook (see `FRONTEND.md`) gets exactly the payload it
expects.
