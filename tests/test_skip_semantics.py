"""Tests for dependency skip-propagation semantics (scene 2 of v1.0 build)."""
from __future__ import annotations

import pytest

import state as state_mod
from executor import run_show
from models import (
    CutRule,
    RetryPolicy,
    Scene,
    SceneState,
    ShowSettings,
    Strategy,
)


def _tool_scene(scene_id: str, depends_on: list | None = None) -> Scene:
    return Scene(
        scene=scene_id,
        title=f"Scene {scene_id}",
        principal=Strategy(method="tool-call", agent="test", action="read-csv",
                           params={"path": "/tmp/fake.csv"}),
        outputs={f"{scene_id}_out": {"type": "list"}},
        success_when={"schema": "contact[]", "min-length": 1},
        depends_on=depends_on or [],
        cut=CutRule(condition="escalate"),
    )


def _failing_scene(scene_id: str, depends_on: list | None = None) -> Scene:
    """Scene that always fails (schema mismatch) and uses cut:continue so the show keeps running."""
    return Scene(
        scene=scene_id,
        title=f"Failing scene {scene_id}",
        principal=Strategy(method="tool-call", agent="test", action="read-csv",
                           params={"path": "/tmp/fake.csv"}),
        outputs={f"{scene_id}_out": {"type": "string"}},
        success_when={"schema": "string"},  # read-csv returns a list → schema check fails
        depends_on=depends_on or [],
        cut=CutRule(condition="continue"),  # cut status, not blocked — show continues
    )


def _make_show(scenes: list, show_id: str = "skip-test") -> ShowSettings:
    return ShowSettings(
        id=show_id,
        title="Skip semantics test",
        running_order=scenes,
    )


def test_failed_dependency_causes_skip_not_blocked(tmp_state_dirs):
    """A scene whose dependency failed should be 'skipped', not 'blocked' or 'cut'."""
    show = _make_show([
        _failing_scene("scene_a"),
        _tool_scene("scene_b", depends_on=["scene_a"]),
    ], show_id="skip-test-1")

    result = run_show(show)

    assert result.scenes["scene_b"].status == "skipped", (
        f"Expected 'skipped', got '{result.scenes['scene_b'].status}'"
    )


def test_skip_reason_recorded_in_scene_state(tmp_state_dirs):
    """When a scene is skipped due to dependency failure, skip_reason is recorded."""
    show = _make_show([
        _failing_scene("scene_a"),
        _tool_scene("scene_b", depends_on=["scene_a"]),
    ], show_id="skip-test-2")

    result = run_show(show)

    sc = result.scenes["scene_b"]
    assert sc.status == "skipped"
    assert sc.skip_reason is not None
    assert "scene_a" in sc.skip_reason


def test_skip_propagates_transitively_through_chain(tmp_state_dirs):
    """Skip propagates through a chain: A fails → B skips → C skips."""
    show = _make_show([
        _failing_scene("scene_a"),
        _tool_scene("scene_b", depends_on=["scene_a"]),
        _tool_scene("scene_c", depends_on=["scene_b"]),
    ], show_id="skip-test-3")

    result = run_show(show)

    assert result.scenes["scene_b"].status == "skipped"
    assert result.scenes["scene_c"].status == "skipped"
    assert result.scenes["scene_c"].skip_reason is not None


def test_non_dependent_scenes_still_run_when_one_skipped(tmp_state_dirs):
    """Independent scenes run normally even when another scene is skipped."""
    show = _make_show([
        _failing_scene("scene_a"),
        _tool_scene("scene_b", depends_on=["scene_a"]),   # will be skipped
        _tool_scene("scene_c"),                            # no dependency — should run
    ], show_id="skip-test-4")

    result = run_show(show)

    assert result.scenes["scene_b"].status == "skipped"
    assert result.scenes["scene_c"].status in state_mod.SUCCESS_STATES, (
        f"Independent scene_c should have played, got: {result.scenes['scene_c'].status}"
    )
