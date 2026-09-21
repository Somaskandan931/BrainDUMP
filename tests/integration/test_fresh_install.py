"""A brand-new install: empty data dir -> app boots -> first user can register and work."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Runs in a subprocess so it gets a genuinely empty BRAINDUMP_DATA_DIR and its own
# import of the app -- none of the suite's shared engine/TestClient state.
_SCRIPT = textwrap.dedent(
    """
    import json
    from fastapi.testclient import TestClient
    from sqlalchemy import inspect
    from backend.app.db import migrate
    from backend.app.main import app
    from backend.app.db.database import Base, engine

    out = {}
    with TestClient(app) as client:  # lifespan runs init_db() on the empty database
        out["stamped_head"] = migrate.current_revision(engine) == migrate.head_revision()
        out["tables_missing"] = sorted(set(Base.metadata.tables) - set(inspect(engine).get_table_names()))

        reg = client.post("/api/auth/register", json={"email": "first@example.com", "password": "a-decent-password"})
        out["register"] = reg.status_code
        headers = {"Authorization": "Bearer " + reg.json()["access_token"]}

        out["create_task"] = client.post("/api/tasks/", json={"title": "First task"}, headers=headers).status_code
        out["task_titles"] = [t["title"] for t in client.get("/api/tasks/", headers=headers).json()]
        out["calendar_status"] = client.get("/api/calendar/google/status", headers=headers).json()
        out["anonymous_tasks"] = client.get("/api/tasks/").status_code
    print("RESULT" + json.dumps(out))
    """
)


def test_empty_data_dir_boots_and_serves_the_first_user(tmp_path):
    env = {**os.environ, "BRAINDUMP_DATA_DIR": str(tmp_path), "JWT_SECRET_KEY": "fresh-install-test-secret"}
    for key in ("GOOGLE_CALENDAR_CLIENT_ID", "GOOGLE_CALENDAR_CLIENT_SECRET"):
        env.pop(key, None)

    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT], cwd=_REPO_ROOT, env=env, capture_output=True, text=True, timeout=120
    )
    assert proc.returncode == 0, proc.stderr[-2000:]

    result = json.loads(next(l for l in proc.stdout.splitlines() if l.startswith("RESULT"))[len("RESULT"):])
    assert result["stamped_head"] is True
    assert result["tables_missing"] == []
    assert result["register"] == 201
    assert result["create_task"] == 201 and result["task_titles"] == ["First task"]
    assert result["calendar_status"] == {"oauth_client_configured": False, "connected": False}
    assert result["anonymous_tasks"] == 401
    assert (tmp_path / "tasks.db").exists()  # the throwaway dir was used, not the real data/
