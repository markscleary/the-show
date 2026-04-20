"""Tests for v0.4.2 patch items: must-complete semantics and programme-delivery state (scene 3)."""
from __future__ import annotations

import pytest

import state as state_mod
from executor import run_show
from models import (
    CutRule,
    RetryPolicy,
    Scene,
    ShowSettings,
    Strategy,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _success_scene(scene_id: str) -> Scene:
    return Scene(
        scene=scene_id,
        title=f"Success scene {scene_id}",
        principal=Strategy(method="tool-call", agent="test", action="read-csv",
                           params={"path": "/tmp/fake.csv"}),
        outputs={f"{scene_id}_out": {"type": "list"}},
        success_when={"schema": "contact[]", "min-length": 1},
    )


def _always_failing_must_complete(scene_id: str) -> Scene:
    """A must-complete scene that always fails the schema check."""
    return Scene(
        scene=scene_id,
        title=f"Must-complete failing scene {scene_id}",
        principal=Strategy(method="tool-call", agent="test", action="read-csv",
                           params={"path": "/tmp/fake.csv"}),
        outputs={f"{scene_id}_out": {"type": "string"}},
        success_when={"schema": "string"},  # read-csv returns list → fails
        must_complete=True,
        cut=CutRule(condition="escalate"),  # would escalate but must_complete overrides
    )


def _make_show(scenes: list, show_id: str = "patch-test") -> ShowSettings:
    return ShowSettings(
        id=show_id,
        title="v0.4.2 patch test",
        running_order=scenes,
    )


# ─────────────────────────────────────────────────────────────────────────────
# must-complete tests
# ─────────────────────────────────────────────────────────────────────────────

def test_must_complete_failure_pauses_show(tmp_state_dirs):
    """When a must-complete scene fails, show status becomes 'paused' not 'aborted'."""
    show = _make_show([
        _always_failing_must_complete("scene_a"),
    ], show_id="mc-pause-test")

    result = run_show(show)

    assert result.status == "paused", f"Expected 'paused', got '{result.status}'"
    assert result.scenes["scene_a"].status == "running"


def test_must_complete_resume_retries_scene(tmp_state_dirs):
    """Resuming a paused must-complete show re-runs the must-complete scene."""
    show = _make_show([
        _always_failing_must_complete("scene_a"),
        _success_scene("scene_b"),
    ], show_id="mc-resume-test")

    # First run: scene_a fails (must-complete), show pauses
    first = run_show(show)
    assert first.status == "paused"

    # Load state and resume — scene_a is still "running" so it gets tried again
    resumed_state = state_mod.load_show_state(show.id)
    second = run_show(show, resume_state=resumed_state)

    # Still paused — scene_a always fails
    assert second.status == "paused"
    # scene_b was never reached
    assert second.scenes.get("scene_b") is None or second.scenes["scene_b"].status == "queued"


# ─────────────────────────────────────────────────────────────────────────────
# delivered status tests
# ─────────────────────────────────────────────────────────────────────────────

def test_successful_run_reaches_delivered_in_db(tmp_state_dirs):
    """After a successful run, the DB shows 'delivered' (programme generation succeeded)."""
    show = _make_show([_success_scene("scene_a")], show_id="delivered-test-ok")

    result = run_show(show)

    # In-memory return value is still "completed"
    assert result.status == "completed"

    # DB should show "delivered"
    db_status = state_mod.get_show_status(show.id)
    assert db_status == "delivered", f"Expected 'delivered' in DB, got '{db_status}'"


def test_delivery_failure_keeps_completed_status(tmp_state_dirs, monkeypatch):
    """If programme generation raises, show status stays 'completed' in the DB."""
    import executor as executor_mod

    def _failing_generate(*args, **kwargs):
        raise RuntimeError("simulated programme generation failure")

    monkeypatch.setattr(executor_mod, "generate_programme", _failing_generate)

    show = _make_show([_success_scene("scene_a")], show_id="delivered-test-fail")

    result = run_show(show)

    assert result.status == "completed"
    db_status = state_mod.get_show_status(show.id)
    assert db_status == "completed", (
        f"Expected 'completed' in DB after delivery failure, got '{db_status}'"
    )
