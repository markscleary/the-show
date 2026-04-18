"""Tests for the executor — end-to-end show execution."""
from __future__ import annotations

from pathlib import Path

import pytest

import state
from executor import meets_success, run_show
from loader import load_show


YAML_PATH = Path(__file__).parent.parent / "example_show.yaml"


def test_run_show_completes(tmp_state_dirs, fast_approval):
    show = load_show(YAML_PATH)
    result = run_show(show)
    assert result.status == "completed"


def test_all_scenes_played(tmp_state_dirs, fast_approval):
    show = load_show(YAML_PATH)
    result = run_show(show)
    for scene_id, sc in result.scenes.items():
        assert sc.status in state.SUCCESS_STATES, f"{scene_id}: {sc.status}"


def test_principal_used_for_all(tmp_state_dirs, fast_approval):
    show = load_show(YAML_PATH)
    result = run_show(show)
    for sc in result.scenes.values():
        assert sc.selected_strategy is not None


def test_cost_recorded(tmp_state_dirs, fast_approval):
    show = load_show(YAML_PATH)
    result = run_show(show)
    assert result.total_cost_usd > 0


def test_events_written_to_db(tmp_state_dirs, fast_approval):
    show = load_show(YAML_PATH)
    run_show(show)
    events = state.get_events(show.id)
    event_types = [ev["event_type"] for ev in events]
    assert "show_started" in event_types
    assert "show_finished" in event_types
    assert "scene_played" in event_types


def test_idempotency_key_event_present(tmp_state_dirs, fast_approval):
    show = load_show(YAML_PATH)
    run_show(show)
    events = state.get_events(show.id)
    idem_events = [ev for ev in events if ev["event_type"] == "idempotency_key_attached"]
    # write_output uses write-json which is side-effectful
    assert len(idem_events) >= 1


def test_urgent_contact_resolved_event(tmp_state_dirs, fast_approval):
    """human-approval scene should produce an urgent_contact_resolved event (APPROVE)."""
    show = load_show(YAML_PATH)
    run_show(show)
    events = state.get_events(show.id)
    resolved = [ev for ev in events if ev["event_type"] == "urgent_contact_resolved"]
    assert len(resolved) == 1
    assert resolved[0]["scene_id"] == "approve_run"
    assert resolved[0]["payload"]["resolution"] == "APPROVE"


def test_outputs_in_db(tmp_state_dirs, fast_approval):
    show = load_show(YAML_PATH)
    run_show(show)
    outputs = state.load_scene_outputs(show.id)
    assert "contacts" in outputs.get("load_targets", {})
    assert "enriched_contacts" in outputs.get("enrich_contacts", {})


def test_cascading_dependency_failure(tmp_state_dirs):
    """A scene dependent on blocked-no-response should be cascading-dependency-failure."""
    show = load_show(YAML_PATH)
    s = state.initialize_state(show)
    s.status = "running"
    # Simulate load_targets ending in blocked-no-response
    s.scenes["load_targets"].status = "blocked-no-response"
    state.persist_state(s)

    from executor import run_show as _run_show
    result = _run_show(show, resume_state=s)

    # approve_run depends on load_targets — should cascade
    assert result.scenes["approve_run"].status == "cascading-dependency-failure"


# ── meets_success unit tests ──────────────────────────────────────────────────

def test_meets_success_no_criteria():
    assert meets_success("anything", {}) is True


def test_meets_success_min_length_pass():
    assert meets_success([1, 2, 3], {"min-length": 3}) is True


def test_meets_success_min_length_fail():
    assert meets_success([1, 2], {"min-length": 3}) is False


def test_meets_success_schema_list():
    assert meets_success([1, 2], {"schema": "contact[]"}) is True
    assert meets_success({"a": 1}, {"schema": "contact[]"}) is False


def test_meets_success_schema_string():
    assert meets_success("hello", {"schema": "string"}) is True
    assert meets_success(42, {"schema": "string"}) is False


def test_meets_success_schema_dict():
    assert meets_success({"a": 1}, {"schema": "contact"}) is True
    assert meets_success([1], {"schema": "contact"}) is False


def test_meets_success_none_fails():
    assert meets_success(None, {}) is False
    assert meets_success(None, {"schema": "string"}) is False
