"""
Manual Milestone 8 verification script — exercises
backend/services/analytics_service.py and backend/ml/trainer.py /
estimator.py directly against a throwaway SQLite DB, monkeypatching the
Ollama call (no local model available in this environment) the same way
manual_milestone6_check.py monkeypatches Google Calendar.

Not a pytest suite (Milestone 9 — Testing and Docker — is where this
project gets a real one); run directly with
`python -m tests.manual_milestone8_check` from ai_os/.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend import config
from backend.database import Base, SessionLocal, engine
from backend.models.calendar_event import CalendarEvent
from backend.models.enums import EventSource, Importance, TaskStatus
from backend.models.metrics import ProductivityMetric
from backend.models.prediction import Prediction
from backend.models.project import Project
from backend.models.session import WorkSession
from backend.models.task import Task
from backend.ml import estimator, trainer
from backend.services import analytics_service
from backend.ai import ollama_client

# Fresh schema each run.
import backend.models  # noqa: F401 registers models

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

db = SessionLocal()
now = datetime.now(timezone.utc)
today = now.date()

print("=== Seeding history ===")

project = Project(name="SourceUp")
db.add(project)
db.commit()
db.refresh(project)

# 25 resolved predictions across the project, all underestimated by ~30%,
# so estimation_error/weekly_review have a real, unambiguous bias to
# report, and trainer.py clears MIN_TRAINING_SAMPLES (20).
for i in range(25):
    task = Task(
        title=f"SourceUp task {i}",
        project_id=project.id,
        importance=Importance.HIGH,
        status=TaskStatus.COMPLETED,
        estimated_hours=2.0,
        actual_hours=2.6,
        completed_at=now - timedelta(days=i % 6),
    )
    db.add(task)
    db.commit()
    db.refresh(task)

    prediction = Prediction(
        task_id=task.id,
        category=str(project.id),
        predicted_hours=2.0,
        actual_hours=2.6,
        error_pct=30.0,
        resolved_at=now - timedelta(days=i % 6),
    )
    db.add(prediction)

db.commit()

# Two ProductivityMetric rows (today + yesterday) so weekly_review /
# streaks have something to roll up, with today's tasks_planned coming
# from a real CalendarEvent count (Milestone 8 change to nightly.py).
today_task = Task(title="Finish CV Assignment Q2", importance=Importance.CRITICAL, status=TaskStatus.COMPLETED, completed_at=now)
db.add(today_task)
db.commit()
db.refresh(today_task)

db.add(
    CalendarEvent(
        task_id=today_task.id,
        title=today_task.title,
        start_time=now - timedelta(hours=1),
        end_time=now,
        source=EventSource.BRAIN_DUMP,
    )
)
db.add(ProductivityMetric(date=today, hours_worked=3.0, tasks_completed=1, tasks_planned=1, completion_rate=1.0))
db.add(ProductivityMetric(date=today - timedelta(days=1), hours_worked=1.5, tasks_completed=1, tasks_planned=2, completion_rate=0.5))
db.commit()

# A WorkSession so productivity_hours has a real bucket to report.
db.add(
    WorkSession(
        task_id=today_task.id,
        start_time=now.replace(hour=20, minute=0, second=0, microsecond=0),
        end_time=now.replace(hour=21, minute=0, second=0, microsecond=0),
        duration_minutes=60,
    )
)
db.commit()

print("=== ml/trainer.py ===")

result = trainer.train_estimator(db)
print(f"train_estimator -> trained={result.trained} sample_count={result.sample_count} "
      f"MAE={result.mean_absolute_error_hours} (expect trained=True, sample_count=25)")
assert result.trained is True and result.sample_count == 25
assert trainer.ESTIMATOR_MODEL_PATH.exists(), "trained model should be persisted to disk"

print("\n=== ml/estimator.py (uses the model just trained) ===")

new_task = Task(title="Brand-new SourceUp task", project_id=None, importance=Importance.HIGH)
predicted, confidence = estimator.estimate_hours(db, new_task)
print(f"estimate_hours (no project, HIGH importance) -> predicted={predicted} confidence={confidence}")
assert predicted > 0

print("\n=== services/analytics_service.py ===")


def fake_call_model(prompt, system=None, **kwargs):
    return "You underestimated SourceUp by 30% this week — start those tasks a day or two earlier."


ollama_client.call_model = fake_call_model
analytics_service.call_model = fake_call_model  # already imported by name into the module

review = analytics_service.weekly_review(db)
print(f"weekly_review -> tasks_completed={review.tasks_completed} hours_worked={review.hours_worked} "
      f"completion_rate={review.completion_rate} ai_generated={review.ai_generated}")
print(f"  recommendation: {review.recommendation!r}")
assert review.tasks_completed == 1
assert review.ai_generated is True
assert "SourceUp" in review.recommendation

error_report = analytics_service.estimation_error(db)
print(f"estimation_error -> overall={error_report.overall_average_error_pct} "
      f"n={error_report.overall_sample_count} by_category={[(c.category, c.average_error_pct, c.bias) for c in error_report.by_category]}")
assert error_report.overall_sample_count == 25
assert error_report.by_category and error_report.by_category[0].category == "SourceUp"
assert error_report.by_category[0].bias == "underestimates"

streak_report = analytics_service.streaks(db)
print(f"streaks -> current={streak_report.current_streak_days} longest={streak_report.longest_streak_days} "
      f"active_today={streak_report.active_today}")
assert streak_report.active_today is True
assert streak_report.current_streak_days >= 2  # today + yesterday both have tasks_completed > 0

hours_report = analytics_service.productivity_hours(db)
logged_hour = next(b for b in hours_report.by_hour if b.hour == 20)
print(f"productivity_hours -> hour 20 -> hours_logged={logged_hour.hours_logged} best_hour={hours_report.best_hour}")
assert logged_hour.hours_logged == 1.0
assert hours_report.best_hour == 20

print("\n=== Fallback: no Ollama available ===")


def raising_call_model(prompt, system=None, **kwargs):
    raise ollama_client.OllamaError("Ollama not running (simulated)")


analytics_service.call_model = raising_call_model
fallback_review = analytics_service.weekly_review(db)
print(f"weekly_review (Ollama down) -> ai_generated={fallback_review.ai_generated}")
print(f"  recommendation: {fallback_review.recommendation!r}")
assert fallback_review.ai_generated is False
assert fallback_review.recommendation  # still non-empty

print("\nALL MILESTONE 8 CHECKS PASSED")

# Clean up the model file this run persisted so repeat runs start fresh.
trainer.ESTIMATOR_MODEL_PATH.unlink(missing_ok=True)

db.close()
