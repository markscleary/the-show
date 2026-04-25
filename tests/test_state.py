"""Tests for the SQLite state layer."""
from __future__ import annotations

from pathlib import Path

import pytest

from the_show import state
from the_show.loader import load_show
from the_show.models import SceneState, ShowState


YAML_PATH = Path(__file__).parent.parent / "example_show.yaml"


def test_initialize_creates_db(tmp_state_dirs):
    show = load_show(YAML_PATH)
    s = state.initialize_state(show)
    assert state.get_db_path(show.id).exists()
    assert s.show_id == show.id
    assert s.status == "planned"
    assert len(s.scenes) == 5


def test_all_scenes_queued_after_init(tmp_state_dirs):
    show = load_show(YAML_PATH)
    s = state.initialize_state(show)
    for sc in s.scenes.values():
        assert sc.status == "queued"


def test_persist_and_load_show_state(tmp_state_dirs):
    show = load_show(YAML_PATH)
    s = state.initialize_state(show)
    s.status = "running"
    s.total_cost_usd = 1.25
    state.persist_show_state(s)

    loaded = state.load_show_state(show.id)
    assert loaded.status == "running"
    assert loaded.total_cost_usd == pytest.approx(1.25)


def test_persist_scene_state(tmp_state_dirs):
    show = load_show(YAML_PATH)
    s = state.initialize_state(show)
    sc = s.scenes["load_targets"]
    sc.status = "played-principal"
    sc.selected_strategy = "principal"
    state.persist_scene_state(show.id, sc)

    loaded = state.load_show_state(show.id)
    assert loaded.scenes["load_targets"].status == "played-principal"
    assert loaded.scenes["load_targets"].selected_strategy == "principal"


def test_persist_and_load_scene_output(tmp_state_dirs):
    show = load_show(YAML_PATH)
    state.initialize_state(show)
    state.persist_scene_output(show.id, "load_targets", "contacts", [{"name": "Alice"}])

    outputs = state.load_scene_outputs(show.id)
    assert outputs["load_targets"]["contacts"] == [{"name": "Alice"}]


def test_load_show_state_restores_outputs(tmp_state_dirs):
    show = load_show(YAML_PATH)
    state.initialize_state(show)
    state.persist_scene_output(show.id, "load_targets", "contacts", [{"name": "Bob"}])

    loaded = state.load_show_state(show.id)
    assert loaded.outputs["load_targets"]["contacts"] == [{"name": "Bob"}]


def test_add_and_get_events(tmp_state_dirs):
    show = load_show(YAML_PATH)
    state.initialize_state(show)
    state.add_event(show.id, "show_started", payload={"show_id": show.id})
    state.add_event(
        show.id, "attempt",
        scene_id="load_targets",
        strategy_label="principal",
        cost=0.1,
        duration_ms=500,
    )

    events = state.get_events(show.id)
    assert len(events) == 2
    assert events[0]["event_type"] == "show_started"
    assert events[1]["event_type"] == "attempt"
    assert events[1]["cost_usd"] == pytest.approx(0.1)


def test_get_events_with_limit(tmp_state_dirs):
    show = load_show(YAML_PATH)
    state.initialize_state(show)
    for i in range(10):
        state.add_event(show.id, f"ev_{i}")
    events = state.get_events(show.id, limit=3)
    assert len(events) == 3


def test_count_completed_scenes(tmp_state_dirs):
    show = load_show(YAML_PATH)
    s = state.initialize_state(show)
    s.scenes["load_targets"].status = "played-principal"
    s.scenes["approve_run"].status = "cut"
    state.persist_state(s)

    completed, total = state.count_completed_scenes(show.id)
    assert completed == 2
    assert total == 5


def test_archive_db(tmp_state_dirs):
    show = load_show(YAML_PATH)
    state.initialize_state(show)
    original = state.get_db_path(show.id)
    assert original.exists()

    abandoned = state.archive_db(show.id)
    assert not original.exists()
    assert abandoned.exists()
    assert "abandoned" in abandoned.name


def test_wal_mode_enabled(tmp_state_dirs):
    show = load_show(YAML_PATH)
    state.initialize_state(show)
    import sqlite3
    conn = sqlite3.connect(str(state.get_db_path(show.id)))
    row = conn.execute("PRAGMA journal_mode;").fetchone()
    conn.close()
    assert row[0] == "wal"
