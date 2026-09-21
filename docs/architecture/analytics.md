# Analytics and ML Components

Implements the read side of the "Learning Model" and "Weekly AI Review"
from the product vision. All four `/api/analytics/*` routes are real
endpoints, and `ml/estimator.py` has a learned second tier on top of
its group-median baseline (see `backend/services/PLANNING.md`).

## What's live

- **`backend/services/analytics_service.py`** — all four analytics
  aggregations, computed live from existing tables on every request (no
  caching layer; see the module docstring for why that's fine for a
  single-user local SQLite install):
  - `weekly_review()` — last 7 days of `ProductivityMetric` rolled up
    into tasks completed/planned, hours worked, most/least productive
    day, most-underestimated category (via `estimation_error()`),
    missed deadlines, and per-project progress. Ends with a one-sentence
    recommendation from the **Weekly Review / Reflection Agent**
    (`ai/prompts.py::WEEKLY_REVIEW_SYSTEM`) — explains numbers that were
    already computed in Python, doesn't compute them itself. Falls back
    to a rule-based sentence (`_rule_based_recommendation()`) if Ollama
    isn't running, so this endpoint never 502s just because the local
    model is offline — `ai_generated: false` on the response signals
    which path produced it.
  - `estimation_error()` — groups resolved `Prediction` rows by category
    (a project name, resolved from `Prediction.category`'s stored
    project id, or an importance tier like `"high"` for one-off tasks),
    averages `error_pct` per group, and labels each `"underestimates"`
    / `"overestimates"` / `"accurate"` against a ±5% noise threshold.
  - `streaks()` — current/longest consecutive-day completion streaks
    from `ProductivityMetric.tasks_completed > 0`, with a same-day grace
    period (a streak alive through yesterday still counts as current
    today, since today isn't over).
  - `productivity_hours()` — buckets `WorkSession.duration_minutes` by
    hour-of-day over a 30-day lookback.
- **`backend/ml/trainer.py`** — `train_estimator()` fits a
  `RandomForestRegressor` on resolved `Prediction` rows (task features:
  importance/energy ordinals, has-project, has-deadline) and persists it
  to `models/estimator.pkl` via `joblib`. Requires 20+ resolved samples;
  below that it's a documented no-op (`trained=False`) rather than
  persisting a model with nothing to learn from.
- **`backend/ml/estimator.py`** — `estimate_hours()` gains a third rung:
  project-specific median (still the best signal when it exists) →
  **trained model** → same-importance-tier median (any project) →
  flat default. The trained model is loaded lazily and reloaded
  automatically if `estimator.pkl`'s mtime changes; a missing or corrupt
  file just skips that rung.
- **`backend/scheduler/nightly.py`** — two fixes/additions:
  - `tasks_planned` (and therefore `completion_rate`) on today's
    `ProductivityMetric` was previously always `None`/`0` — nothing
    populated it. Now computed from a real distinct count of tasks with
    a Brain-Dump-scheduled `CalendarEvent` today.
  - On Sundays, calls `ml.trainer.train_estimator()` — the one part of
    this expensive enough to not redo per-request. Wrapped in a broad
    `except Exception` so an ML failure (missing optional dep, corrupt
    `models/` dir) degrades this one step, not the rest of the nightly
    job (replan, calendar sync).
- **`backend/api/analytics.py`** / **`schemas/analytics.py`** — thin
  routing layer; all real logic lives in the service module above, same
  pattern as every other API module in this repo.

## Design decisions

- **Live aggregation, not a cached report.** All four routes query
  SQLite directly on each request. There's no multi-tenant load concern
  for a single-user local install that would justify a caching layer,
  and "always reflects the current DB state" is a simpler contract than
  cache invalidation.
- **The Reflection Agent explains, it doesn't compute.** Every number in
  `WeeklyReviewResponse` is deterministic Python/SQL; the model only
  turns an already-correct stats dict into one readable sentence
  (`json_mode=False` — this is the only prose, non-JSON, agent call in
  the codebase; every other agent uses `call_model_json()`). This keeps
  the numbers trustworthy regardless of what a local 8B model does with
  them, and keeps the failure mode (Ollama down) a missing sentence, not
  wrong statistics.
- **Priority engine stays hand-tuned, on purpose.** `ml/priority_model.py`
  wasn't given a learned counterpart here, even though its own
  docstring flagged that as the eventual plan. Re-weighting its five
  components would need labeled "what did the user actually work on
  next, and why" data broken down *per component* — the schema today
  only stores the composite `priority_score`
  (`Task.priority_score` / `Prediction.predicted_priority_score`), not
  the five inputs that produced it. Learning better weights from a
  composite score alone isn't a real fit; storing the component
  breakdown is a schema change, not something to smuggle in as a
  half-measure. Documented as real future scope in `ml/trainer.py`'s
  module docstring instead.
- **Estimator training is scheduled, not on-demand.** `train_estimator()`
  is only ever called from the Sunday nightly job (or manually via
  `python -m backend.ml.trainer`) — never from a request path. Task
  history for a single user changes slowly enough that daily/per-request
  retraining buys nothing and just costs a full table scan + model fit
  every time.
- **`Prediction.category` string parsing, not a real foreign key.**
  `estimation_error()`'s `_category_display_name()` has to sniff whether
  `category` is a stringified project id (`"7"`) or an importance label
  (`"high"`) because that's how `ml/estimator.py::ensure_estimate()`
  already writes it — not a pattern introduced here, but worth flagging
  as something a real schema (e.g. a nullable `project_id` FK plus a
  separate `importance_fallback` column) would avoid. Left as-is rather
  than migrating a live column for a cosmetic improvement.

## Verified

A manual check script seeds 25 resolved `Prediction` rows (consistently
~30% underestimated) plus two days of `ProductivityMetric` and a
`WorkSession`, then: trains the estimator and confirms it persists and
reports the right sample count; confirms `estimate_hours()` on a fresh
task actually uses the newly trained model; confirms `weekly_review()`
picks up the underestimation bias and produces an AI-generated
recommendation (Ollama call monkeypatched, same pattern used for the
Google Calendar mocks); confirms `estimation_error()` correctly resolves
the numeric category back to the project name and labels it
`"underestimates"`; confirms `streaks()` and `productivity_hours()` read
back exactly what was seeded; and confirms `weekly_review()` falls back
to a non-empty, `ai_generated: false` recommendation when the Ollama
call raises `OllamaError`.

Only static `py_compile` syntax checks were run in the environment this
was authored in (no network access to install the dependency stack —
fastapi/sqlalchemy/scikit-learn weren't available). Run the manual check
script from `ai_os/` in a real environment before trusting this the way
earlier backend work was verified.
