"""ml/priority_model.py — component breakdown and the composite score."""

from __future__ import annotations

import pytest

from backend.app.core import config
from backend.app.ml.priority_model import compute_priority_components, compute_priority_score
from backend.app.models.enums import Importance
from tests.helpers import make_project, make_task, utcnow

COMPONENT_KEYS = {"deadline_risk", "importance", "estimated_hours", "context_switch_cost", "energy_fit"}


def test_components_expose_the_five_factors_in_unit_range(db):
    task = make_task(db, importance=Importance.HIGH, deadline_in_days=2, estimated_hours=3)
    components = compute_priority_components(task, now=utcnow(), context_switch_cost=0.4)

    assert set(components) == COMPONENT_KEYS
    assert all(0.0 <= v <= 1.0 for v in components.values())


def test_score_is_the_weighted_sum_of_components(db):
    task = make_task(db, importance=Importance.HIGH, deadline_in_days=3, estimated_hours=2)
    now = utcnow()
    components = compute_priority_components(task, now=now, context_switch_cost=0.4)
    weights = config.PRIORITY_WEIGHTS

    expected = sum(
        weights[name] * ((1.0 - value) if name == "context_switch_cost" else value)
        for name, value in components.items()
    )
    assert compute_priority_score(task, now=now, context_switch_cost=0.4) == pytest.approx(expected, abs=1e-3)


def test_switching_projects_lowers_priority_not_raises_it(db):
    """Regression: context_switch_cost is a penalty. It used to be summed as-is,
    so a full project switch *raised* a task's score."""
    task = make_task(db, importance=Importance.MEDIUM, deadline_in_days=3, estimated_hours=2)
    now = utcnow()

    continuing = compute_priority_score(task, now=now, context_switch_cost=config.CONTEXT_SWITCH_SAME_PROJECT_COST)
    switching = compute_priority_score(task, now=now, context_switch_cost=config.CONTEXT_SWITCH_DIFFERENT_PROJECT_COST)

    assert continuing > switching


def test_nearer_deadline_scores_higher(db):
    soon = make_task(db, "soon", deadline_in_days=1, estimated_hours=2)
    later = make_task(db, "later", deadline_in_days=9, estimated_hours=2)
    now = utcnow()

    assert compute_priority_score(soon, now=now, context_switch_cost=0.4) > compute_priority_score(
        later, now=now, context_switch_cost=0.4
    )


def test_critical_overdue_task_stays_within_unit_range(db):
    task = make_task(db, importance=Importance.CRITICAL, deadline_in_days=-3, estimated_hours=0.25)
    score = compute_priority_score(task, now=utcnow(), context_switch_cost=0.0)
    assert 0.0 <= score <= 1.0


def test_same_project_follow_up_has_no_switch_cost(db):
    from backend.app.ml.priority_model import compute_context_switch_cost

    project = make_project(db)
    a = make_task(db, "a", project=project)
    b = make_task(db, "b", project=project)
    other = make_task(db, "other", project=make_project(db, "Other"))

    assert compute_context_switch_cost(b, a) == config.CONTEXT_SWITCH_SAME_PROJECT_COST
    assert compute_context_switch_cost(other, a) == config.CONTEXT_SWITCH_DIFFERENT_PROJECT_COST
    assert compute_context_switch_cost(a, None) == config.CONTEXT_SWITCH_NO_PROJECT_COST
