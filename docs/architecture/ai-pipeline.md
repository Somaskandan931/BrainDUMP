# AI Agents — design notes

## What's real vs. what's still a stub

| File | Status |
|---|---|
| `ai/ollama_client.py` | Real — transport layer, JSON-mode, retries |
| `ai/prompts.py` | Real — Task Parser + Goal Breakdown prompts |
| `services/task_parser.py` | Real — backs `POST /api/planner/brain-dump` |
| `services/planner_service.py` | Real (Goal Engine slice) — backs `POST /api/planner/goal` |
| `ai/memory.py` | Still a stub |
| `ai/embeddings.py` | Still a stub |

## Two agents, not eight

`ai/prompts.py`'s original docstring listed eight agents (Task Parser,
Task Breakdown, Deadline Generator, Scheduler, Priority Engine, Weekly
Review, Daily Planner, Reflection Agent). Two are LLM-backed agents in
this layer:

- **Task Parser** — `POST /api/planner/brain-dump`. Free text in,
  `{"tasks": [...]}` out.
- **Goal Breakdown** ("Goal Engine" in `models/project.py`'s vocabulary)
  — `POST /api/planner/goal`. One goal in, a Project + ordered Task
  roadmap out.

Scheduler and Priority Engine are classical models in `backend/ml/*`
rather than LLM calls (see the `ai/` vs `ml/` split in the main
`ARCHITECTURE.md`) — priority and scheduling need to be fast,
deterministic, and retrainable on the user's own
`WorkSession`/`Prediction` history, which an LLM call isn't well suited
for. Weekly Review / Reflection Agent lives with the analytics layer
(see `ANALYTICS.md`), once there's enough `productivity_metrics`
history for it to say something useful.

## Deadline Generator was folded into Task Parser, not built separately

The original plan was a chained pipeline: Task Parser extracts tasks,
then a separate Deadline Generator agent resolves relative dates
("next Friday") against each task. In practice that's two local
inference calls per brain dump for output that fits naturally into one
JSON schema. `TASK_PARSER_SYSTEM` in `ai/prompts.py` is given the
current date/time and asked to resolve deadlines itself as part of the
same response. If deadline resolution turns out to need more context
than the Task Parser prompt naturally carries (e.g. checking against
existing calendar load), it can still be split out later — the JSON
schema change would be additive, not breaking.

## Why `ai/memory.py` and `ai/embeddings.py` are still stubs

Both were originally scoped as part of this feature set, but neither is
required for brain-dump or goal parsing to work correctly at the scale
this system runs at (a personal, single-user planner, not a
multi-session support bot):

- `ai/memory.py` (short-term session context) matters once brain dumps
  routinely reference earlier ones ("also finish Question 3" needs to
  know which assignment that is). The current Task Parser only
  resolves what's inside the current text.
- `ai/embeddings.py` (FAISS semantic search) matters once there are
  enough tasks/projects that exact-name project matching in
  `task_parser._resolve_project()` starts missing near-duplicates
  ("SourceUp" vs "Source Up project"). Case-insensitive exact match is
  enough for now.

Both stay as documented, unimplemented stubs rather than being deleted
or half-built, so there's an obvious, already-scoped place for them to
land later.

## Error handling: two distinct failure modes, two status codes

`ai/ollama_client.OllamaError` covers both "Ollama isn't running /
timed out" and "Ollama responded but the JSON was malformed" —
transport and content failures at the model layer. `TaskParserError`
and `PlannerServiceError` cover a different thing: the model responded
with valid JSON, but the *content* wasn't usable (e.g. an empty task
list for a brain dump with nothing actionable in it).

`services/task_parser.py` and `services/planner_service.py`
deliberately let `OllamaError` propagate unwrapped rather than catching
and re-raising it as their own error type — an early version of this
code did wrap it, and a test written against the API layer caught the
bug: wrapping collapsed "Ollama is down" (not the user's fault, should
be `502`) into the same error type as "nothing to parse" (arguably the
user's fault, `422`), so `api/planner.py` couldn't tell them apart and
both surfaced as `422`. `api/planner.py` now catches both exception
types separately and maps them to different status codes:

```python
except TaskParserError as exc:
    raise HTTPException(status_code=422, detail=str(exc))
except OllamaError as exc:
    raise HTTPException(status_code=502, detail=f"Ollama unavailable: {exc}")
```

## Testing without a live Ollama server

This sandbox has no local Ollama instance to call, so `ai/ollama_client.py`
itself wasn't exercised end-to-end here — it's a direct, thin wrapper
around the `ollama` package's documented `.chat()` call, matching the
same pattern used elsewhere in this codebase. What *was* exercised,
by monkeypatching `call_model_json` at the service-layer boundary and
running through `TestClient(app)`:

- brain-dump: project dedup (case-insensitive, across calls), skipping
  malformed task entries without failing the batch, unparseable
  deadline strings falling back to `None` instead of crashing, unknown
  project association leaving `project_id=None`
- goal breakdown: tasks returned sorted by the model's `order` field
  (not JSON array order), `deadline_offset_days` converted correctly,
  a failed breakdown rolling back the `Project` row instead of leaving
  an orphan
- both empty-result and Ollama-transport-failure error paths, and that
  they map to the correct HTTP status codes (`422` vs `502`) through
  the real FastAPI routes
- no regression on the existing CRUD routes

When you have Ollama running locally, the one thing worth manually
sanity-checking that these tests can't cover: does `qwen3:8b` (or
whichever model you pull) reliably follow the JSON schema in
`TASK_PARSER_SYSTEM` / `TASK_BREAKDOWN_SYSTEM` well enough in practice,
or does the prompt need tightening for your model's actual behavior.
