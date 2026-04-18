"""Tests for crash-resume behaviour."""
from __future__ import annotations

from pathlib import Path

import pytest

import state
from executor import run_show
from loader import load_show


YAML_PATH = Path(__file__).parent.parent / "example_show.yaml"


def test_resume_skips_completed_scenes(tmp_state_dirs, fast_approval):
    """If a scene is already in a terminal state, the executor must not re-run it."""
    show = load_show(YAML_PATH)
    # Manually set up "interrupted" state: load_targets played, rest queued
    s = state.initialize_state(show)
    s.status = "running"
    s.scenes["load_targets"].status = "played-principal"
    s.scenes["load_targets"].selected_strategy = "principal"
    state.persist_scene_output(show.id, "load_targets", "contacts",
                               [{"name": f"C{i}", "email": f"c{i}@ex.com"} for i in range(60)])
    state.persist_state(s)

    # Load from DB and resume
    resume = state.load_show_state(show.id)
    result = run_show(show, resume_state=resume)

    assert result.status == "completed"
    # load_targets must still be played-principal (not re-executed)
    assert result.scenes["load_targets"].status == "played-principal"
    # remaining scenes should have completed
    for scene_id in ["approve_run", "enrich_contacts", "filter_contacts", "write_output"]:
        assert result.scenes[scene_id].status in state.SUCCESS_STATES, (
            f"{scene_id} expected success, got {result.scenes[scene_id].status}"
        )


def test_resume_preserves_cost(tmp_state_dirs, fast_approval):
    """Costs accumulated before a crash should survive the resume."""
    show = load_show(YAML_PATH)
    s = state.initialize_state(show)
    s.status = "running"
    s.total_cost_usd = 0.50  # already spent before crash
    s.scenes["load_targets"].status = "played-principal"
    s.scenes["load_targets"].selected_strategy = "principal"
    state.persist_state(s)
    state.persist_scene_output(show.id, "load_targets", "contacts",
                               [{"name": f"C{i}"} for i in range(60)])

    resume = state.load_show_state(show.id)
    assert resume.total_cost_usd == pytest.approx(0.50)
    result = run_show(show, resume_state=resume)
    # Cost should be at least what was there before (sub-agent adds more)
    assert result.total_cost_usd >= 0.50


def test_fresh_start_after_completed(tmp_state_dirs, fast_approval):
    """Running a completed show with archive_db + re-initialize should start clean."""
    show = load_show(YAML_PATH)
    run_show(show)

    # Archive the old DB
    abandoned = state.archive_db(show.id)
    assert abandoned.exists()
    assert not state.show_exists(show.id)

    # Start fresh
    result = run_show(show)
    assert result.status == "completed"


def test_load_show_state_raises_on_missing(tmp_state_dirs):
    with pytest.raises(ValueError, match="No state found"):
        state.load_show_state("nonexistent-show")


def test_terminal_states_are_skipped(tmp_state_dirs, mock_dirs):
    """Scenes already in TERMINAL_STATES must not be re-executed on resume."""
    show = load_show(YAML_PATH)
    s = state.initialize_state(show)
    s.status = "running"
    # Mark first four scenes as played (terminal + success) so write_output can run
    for scene_id in ["load_targets", "approve_run", "enrich_contacts"]:
        s.scenes[scene_id].status = "played-principal"
        s.scenes[scene_id].selected_strategy = "principal"
    s.scenes["filter_contacts"].status = "played-partial"  # partial but still a success state
    s.scenes["filter_contacts"].selected_strategy = "principal"
    # Provide the output write_output depends on
    state.persist_scene_output(
        show.id, "filter_contacts", "qualified_contacts",
        [{"name": f"Q{i}", "title": "T", "website": "https://ex.com"} for i in range(15)],
    )
    state.persist_state(s)

    resume = state.load_show_state(show.id)
    result = run_show(show, resume_state=resume)

    # The pre-completed scenes must not have been re-executed
    assert result.scenes["load_targets"].status == "played-principal"
    assert result.scenes["filter_contacts"].status == "played-partial"
    # write_output should have run and succeeded
    assert result.scenes["write_output"].status in state.SUCCESS_STATES
