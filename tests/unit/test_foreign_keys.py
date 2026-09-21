"""SQLite ignores every ON DELETE CASCADE/SET NULL in the schema unless
`PRAGMA foreign_keys=ON` is set per-connection (see database.py's
_enable_sqlite_foreign_keys connect-listener). These tests delete rows
with a raw SQL DELETE -- deliberately bypassing SQLAlchemy's own
`cascade="all, delete-orphan"` relationship option -- so a regression
that removes or breaks the pragma listener is caught even though the
ORM-level cascade would otherwise silently paper over it.
"""

from __future__ import annotations

from sqlalchemy import text

from backend.app.auth.token_service import issue_refresh_token
from backend.app.db.database import SessionLocal, engine, owner_id
from backend.app.models.dependency import Dependency
from backend.app.models.prediction import Prediction
from backend.app.models.refresh_token import RefreshToken
from backend.app.models.session import WorkSession
from backend.app.models.task import Subtask, Task
from backend.app.services.workspace.activity_service import log_activity
from tests.helpers import make_project, make_task, make_user


def test_foreign_key_enforcement_is_actually_on():
    """The precondition every other test in this file relies on."""
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1


def test_deleting_a_project_cascades_its_tasks(db):
    project = make_project(db, "Doomed project")
    task = make_task(db, "Orphan-to-be", project=project)
    task_id = task.id

    with engine.connect() as conn:
        conn.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project.id})
        conn.commit()

    with SessionLocal() as session:
        assert session.get(Task, task_id) is None


def test_deleting_a_task_cascades_subtasks_sessions_predictions_and_dependencies(db):
    from datetime import datetime, timezone

    task = make_task(db, "Parent task")
    other = make_task(db, "Dependency target")

    subtask = Subtask(user_id=owner_id(db), task_id=task.id, title="Sub")
    session_row = WorkSession(
        user_id=owner_id(db), task_id=task.id, start_time=datetime.now(timezone.utc)
    )
    prediction = Prediction(
        user_id=owner_id(db), task_id=task.id, category="deep_work", predicted_hours=1.0
    )
    dependency = Dependency(user_id=owner_id(db), task_id=task.id, depends_on_task_id=other.id)

    db.add_all([subtask, session_row, prediction, dependency])
    db.commit()
    subtask_id = subtask.id
    session_id = session_row.id
    prediction_id = prediction.id
    dependency_id = dependency.id
    task_id = task.id

    with engine.connect() as conn:
        conn.execute(text("DELETE FROM tasks WHERE id = :id"), {"id": task_id})
        conn.commit()

    with SessionLocal() as session:
        assert session.get(Subtask, subtask_id) is None
        assert session.get(WorkSession, session_id) is None
        assert session.get(Prediction, prediction_id) is None
        assert session.get(Dependency, dependency_id) is None
        # The task on the other side of the dependency is untouched.
        assert session.get(Task, other.id) is not None


def test_deleting_a_user_cascades_projects_tasks_refresh_tokens_and_activity_log():
    user = make_user("cascade-user@example.com", "Cascade User")
    session = SessionLocal()
    session.info["user_id"] = user.id
    try:
        project = make_project(session, "User's project")
        task = make_task(session, "User's task", project=project)
        log_activity(session, user_id=user.id, action="task.created", entity_type="task", entity_id=task.id)
        session.commit()
        project_id, task_id = project.id, task.id
    finally:
        session.close()

    with SessionLocal() as token_session:
        issue_refresh_token(token_session, user.id)

    with engine.connect() as conn:
        conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user.id})
        conn.commit()

    with SessionLocal() as verify:
        from backend.app.models.activity import ActivityLog
        from backend.app.models.project import Project

        assert verify.get(Project, project_id) is None
        assert verify.get(Task, task_id) is None
        assert verify.query(RefreshToken).filter(RefreshToken.user_id == user.id).count() == 0
        assert verify.query(ActivityLog).filter(ActivityLog.user_id == user.id).count() == 0
