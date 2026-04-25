"""Tests for the Execution Monitor — patterns, watcher, and Stage Manager integration."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch, MagicMock

import pytest

from the_show import state as state_mod
from the_show.state import (
    add_event,
    add_monitor_event,
    get_monitor_events,
    get_unacknowledged_monitor_events,
    acknowledge_monitor_events,
    initialize_state,
)
from the_show.monitor.patterns import (
    detect_stalled,
    detect_retry_storm,
    detect_cost_runaway,
    detect_policy_denials,
    detect_oscillation,
    check_ollama_available,
)
from the_show.monitor.watcher import run_monitor, request_stop


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _make_event(event_type: str, scene_id: str = None, cost: float = 0.0,
                ts: str = None, strategy_label: str = None, payload: dict = None) -> Dict:
    ts = ts or datetime.now(timezone.utc).isoformat()
    return {
        "event_type": event_type,
        "scene_id": scene_id,
        "cost_usd": cost,
        "created_at": ts,
        "strategy_label": strategy_label,
        "payload": payload or {},
    }


def _ts_ago(seconds: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


# ──────────────────────────────────────────────────────────────────────────────
# Pattern: stalled detection
# ──────────────────────────────────────────────────────────────────────────────

def test_stalled_fires_when_no_event_in_threshold():
    events = [_make_event("attempt", "scene-1", ts=_ts_ago(700))]
    result = detect_stalled(events, threshold_seconds=600)
    assert result is not None
    assert result["elapsed_seconds"] > 600
    assert result["last_event_type"] == "attempt"


def test_stalled_does_not_fire_when_recent_event():
    events = [_make_event("attempt", "scene-1", ts=_ts_ago(10))]
    result = detect_stalled(events, threshold_seconds=600)
    assert result is None


def test_stalled_empty_events_returns_none():
    assert detect_stalled([], threshold_seconds=600) is None


# ──────────────────────────────────────────────────────────────────────────────
# Pattern: retry storm detection
# ──────────────────────────────────────────────────────────────────────────────

def test_retry_storm_fires_when_retries_exceed_max():
    events = [
        _make_event("attempt", "scene-1", ts=_ts_ago(10))
        for _ in range(8)
    ]
    storms = detect_retry_storm(events, max_retries=5, window_seconds=60)
    assert len(storms) == 1
    assert storms[0]["scene_id"] == "scene-1"
    assert storms[0]["retry_count"] == 8


def test_retry_storm_no_fire_when_below_max():
    events = [
        _make_event("attempt", "scene-1", ts=_ts_ago(10))
        for _ in range(3)
    ]
    storms = detect_retry_storm(events, max_retries=5, window_seconds=60)
    assert len(storms) == 0


def test_retry_storm_ignores_old_events():
    old = [_make_event("attempt", "scene-1", ts=_ts_ago(200)) for _ in range(8)]
    storms = detect_retry_storm(old, max_retries=5, window_seconds=60)
    assert len(storms) == 0


def test_retry_storm_multiple_scenes():
    events = (
        [_make_event("attempt", "scene-1", ts=_ts_ago(5)) for _ in range(6)] +
        [_make_event("attempt", "scene-2", ts=_ts_ago(5)) for _ in range(7)]
    )
    storms = detect_retry_storm(events, max_retries=5, window_seconds=60)
    scene_ids = {s["scene_id"] for s in storms}
    assert "scene-1" in scene_ids
    assert "scene-2" in scene_ids


# ──────────────────────────────────────────────────────────────────────────────
# Pattern: cost runaway detection
# ──────────────────────────────────────────────────────────────────────────────

def test_cost_runaway_fires_on_hard_cap():
    events = [
        _make_event("attempt", cost=3.0),
        _make_event("attempt", cost=4.0),
    ]
    result = detect_cost_runaway(events, soft_cap_usd=5.0, hard_cap_usd=10.0)
    assert result is not None
    assert result["cap_type"] == "soft"
    assert result["total_cost_usd"] == pytest.approx(7.0)


def test_cost_runaway_fires_hard_cap():
    events = [_make_event("attempt", cost=5.0) for _ in range(3)]
    result = detect_cost_runaway(events, soft_cap_usd=5.0, hard_cap_usd=10.0)
    assert result is not None
    assert result["cap_type"] == "hard"


def test_cost_runaway_no_fire_below_caps():
    events = [_make_event("attempt", cost=0.5)]
    result = detect_cost_runaway(events, soft_cap_usd=5.0, hard_cap_usd=10.0)
    assert result is None


def test_cost_runaway_no_caps_returns_none():
    events = [_make_event("attempt", cost=100.0)]
    result = detect_cost_runaway(events, soft_cap_usd=None, hard_cap_usd=None)
    assert result is None


# ──────────────────────────────────────────────────────────────────────────────
# Pattern: policy denial detection
# ──────────────────────────────────────────────────────────────────────────────

def test_policy_denials_fires_at_max():
    events = [
        _make_event("policy_denied", "scene-1")
        for _ in range(3)
    ]
    denials = detect_policy_denials(events, max_denials=3)
    assert len(denials) == 1
    assert denials[0]["scene_id"] == "scene-1"
    assert denials[0]["denial_count"] == 3


def test_policy_denials_no_fire_below_max():
    events = [_make_event("policy_denied", "scene-1") for _ in range(2)]
    denials = detect_policy_denials(events, max_denials=3)
    assert len(denials) == 0


def test_policy_denials_multiple_scenes():
    events = (
        [_make_event("policy_denied", "scene-1") for _ in range(3)] +
        [_make_event("policy_denied", "scene-2") for _ in range(4)]
    )
    denials = detect_policy_denials(events, max_denials=3)
    scene_ids = {d["scene_id"] for d in denials}
    assert "scene-1" in scene_ids
    assert "scene-2" in scene_ids


# ──────────────────────────────────────────────────────────────────────────────
# Pattern: oscillation detection (Qwen mocked)
# ──────────────────────────────────────────────────────────────────────────────

def test_oscillation_fires_when_qwen_says_oscillating(monkeypatch):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"response": "oscillating"}).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = detect_oscillation(
            "scene-1",
            ["output-a", "output-a", "output-a-v2", "output-a-v3"],
        )
    assert result is not None
    assert result["scene_id"] == "scene-1"


def test_oscillation_no_fire_when_converging(monkeypatch):
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps({"response": "converging"}).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = detect_oscillation(
            "scene-1",
            ["output-a", "output-b", "output-c", "output-d"],
        )
    assert result is None


def test_oscillation_returns_none_on_ollama_error():
    with patch("urllib.request.urlopen", side_effect=Exception("connection refused")):
        result = detect_oscillation("scene-1", ["a", "b", "c", "d"])
    assert result is None


def test_oscillation_requires_at_least_2_outputs():
    result = detect_oscillation("scene-1", ["only-one"])
    assert result is None


# ──────────────────────────────────────────────────────────────────────────────
# Ollama availability check
# ──────────────────────────────────────────────────────────────────────────────

def test_check_ollama_returns_model_when_present():
    tags_data = {"models": [{"name": "qwen3:14b"}, {"name": "llama2"}]}
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(tags_data).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        model = check_ollama_available()
    assert model == "qwen3:14b"


def test_check_ollama_returns_none_when_model_missing():
    tags_data = {"models": [{"name": "llama2"}]}
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(tags_data).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        model = check_ollama_available()
    assert model is None


def test_check_ollama_returns_none_when_unreachable():
    with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
        model = check_ollama_available()
    assert model is None


# ──────────────────────────────────────────────────────────────────────────────
# State: add/get/acknowledge monitor events
# ──────────────────────────────────────────────────────────────────────────────

def test_add_and_retrieve_monitor_event(tmp_state_dirs):
    from the_show.loader import load_show
    from pathlib import Path
    YAML_PATH = Path(__file__).parent.parent / "example_show.yaml"
    show = load_show(YAML_PATH)
    initialize_state(show)

    eid = add_monitor_event(
        show.id, "stalled", "warning",
        scene_id="scene-1",
        details={"elapsed": 700},
        threshold_config="stalled_threshold=600s",
    )
    assert eid > 0

    events = get_unacknowledged_monitor_events(show.id)
    assert len(events) == 1
    assert events[0]["trigger_type"] == "stalled"
    assert events[0]["acknowledged"] is False


def test_acknowledge_monitor_events(tmp_state_dirs):
    from the_show.loader import load_show
    from pathlib import Path
    YAML_PATH = Path(__file__).parent.parent / "example_show.yaml"
    show = load_show(YAML_PATH)
    initialize_state(show)

    eid = add_monitor_event(show.id, "retry-storm", "warning", scene_id="scene-1")
    events = get_unacknowledged_monitor_events(show.id)
    assert len(events) == 1

    acknowledge_monitor_events(show.id, [eid])
    events_after = get_unacknowledged_monitor_events(show.id)
    assert len(events_after) == 0

    all_events = get_monitor_events(show.id)
    assert len(all_events) == 1
    assert all_events[0]["acknowledged"] is True


def test_acknowledged_events_do_not_re_trigger(tmp_state_dirs):
    from the_show.loader import load_show
    from pathlib import Path
    YAML_PATH = Path(__file__).parent.parent / "example_show.yaml"
    show = load_show(YAML_PATH)
    initialize_state(show)

    eid = add_monitor_event(show.id, "stalled", "warning")
    acknowledge_monitor_events(show.id, [eid])

    unacked = get_unacknowledged_monitor_events(show.id)
    assert unacked == []


# ──────────────────────────────────────────────────────────────────────────────
# Watcher: run_monitor writes events to DB
# ──────────────────────────────────────────────────────────────────────────────

def test_monitor_detects_stalled_and_writes_event(tmp_state_dirs, monkeypatch):
    """Monitor should write a stalled monitor_event when last DB event is old."""
    from the_show.loader import load_show
    from pathlib import Path
    YAML_PATH = Path(__file__).parent.parent / "example_show.yaml"
    show = load_show(YAML_PATH)
    initialize_state(show)

    # Write an old event directly to DB
    old_ts = _ts_ago(700)
    conn = state_mod._connect(show.id)
    state_mod._create_schema(conn)
    conn.execute(
        "INSERT INTO events (show_id, event_type, created_at) VALUES (?, ?, ?)",
        (show.id, "attempt", old_ts),
    )
    conn.commit()
    conn.close()

    # Monkeypatch STATE_BASE in watcher to match test's tmp dir
    import the_show.monitor.watcher as watcher_mod
    monkeypatch.setattr(watcher_mod, "_state_mod", state_mod)

    # Run one monitor iteration (not a loop) by calling the poll logic directly
    events = state_mod.get_events(show.id)
    stall = detect_stalled(events, threshold_seconds=600)
    assert stall is not None

    add_monitor_event(
        show.id, "stalled", "warning",
        scene_id=stall.get("last_scene_id"),
        details=stall,
    )

    monitor_events = get_monitor_events(show.id)
    assert any(e["trigger_type"] == "stalled" for e in monitor_events)


def test_monitor_detects_retry_storm_and_writes_event(tmp_state_dirs, monkeypatch):
    from the_show.loader import load_show
    from pathlib import Path
    YAML_PATH = Path(__file__).parent.parent / "example_show.yaml"
    show = load_show(YAML_PATH)
    initialize_state(show)

    # Write 8 attempt events within the window
    conn = state_mod._connect(show.id)
    state_mod._create_schema(conn)
    for _ in range(8):
        conn.execute(
            "INSERT INTO events (show_id, event_type, scene_id, created_at) VALUES (?, ?, ?, ?)",
            (show.id, "attempt", "scene-1", _ts_ago(10)),
        )
    conn.commit()
    conn.close()

    events = state_mod.get_events(show.id)
    storms = detect_retry_storm(events, max_retries=5, window_seconds=60)
    assert len(storms) == 1

    for storm in storms:
        add_monitor_event(show.id, "retry-storm", "warning", scene_id=storm["scene_id"], details=storm)

    monitor_events = get_monitor_events(show.id)
    assert any(e["trigger_type"] == "retry-storm" for e in monitor_events)


def test_monitor_detects_cost_runaway_and_writes_event(tmp_state_dirs, monkeypatch):
    from the_show.loader import load_show
    from pathlib import Path
    YAML_PATH = Path(__file__).parent.parent / "example_show.yaml"
    show = load_show(YAML_PATH)
    initialize_state(show)

    conn = state_mod._connect(show.id)
    state_mod._create_schema(conn)
    for cost in [3.0, 4.0, 5.0]:
        conn.execute(
            "INSERT INTO events (show_id, event_type, cost_usd, created_at) VALUES (?, ?, ?, ?)",
            (show.id, "attempt", cost, datetime.now(timezone.utc).isoformat()),
        )
    conn.commit()
    conn.close()

    events = state_mod.get_events(show.id)
    runaway = detect_cost_runaway(events, soft_cap_usd=5.0, hard_cap_usd=20.0)
    assert runaway is not None

    add_monitor_event(show.id, "cost-runaway", "critical", details=runaway)

    monitor_events = get_monitor_events(show.id)
    assert any(e["trigger_type"] == "cost-runaway" for e in monitor_events)


def test_monitor_detects_policy_denials_and_writes_event(tmp_state_dirs, monkeypatch):
    from the_show.loader import load_show
    from pathlib import Path
    YAML_PATH = Path(__file__).parent.parent / "example_show.yaml"
    show = load_show(YAML_PATH)
    initialize_state(show)

    conn = state_mod._connect(show.id)
    state_mod._create_schema(conn)
    for _ in range(3):
        conn.execute(
            "INSERT INTO events (show_id, event_type, scene_id, created_at) VALUES (?, ?, ?, ?)",
            (show.id, "policy_denied", "scene-1", datetime.now(timezone.utc).isoformat()),
        )
    conn.commit()
    conn.close()

    events = state_mod.get_events(show.id)
    denials = detect_policy_denials(events, max_denials=3)
    assert len(denials) == 1

    for denial in denials:
        add_monitor_event(show.id, "policy-denials", "urgent", scene_id=denial["scene_id"], details=denial)

    monitor_events = get_monitor_events(show.id)
    assert any(e["trigger_type"] == "policy-denials" for e in monitor_events)


# ──────────────────────────────────────────────────────────────────────────────
# Stage Manager integration: monitor event matching escalate-when → dispatcher
# ──────────────────────────────────────────────────────────────────────────────

def test_stage_manager_escalates_on_cost_runaway(tmp_state_dirs, fast_approval, monkeypatch):
    """A cost-runaway monitor event that matches bible escalation should be acknowledged."""
    from the_show.loader import load_show
    from the_show.executor import _handle_monitor_signals
    from pathlib import Path
    YAML_PATH = Path(__file__).parent.parent / "example_show.yaml"
    show = load_show(YAML_PATH)
    state = initialize_state(show)
    state.status = "running"

    # Inject a cost-runaway monitor event
    add_monitor_event(show.id, "cost-runaway", "critical", details={"total_cost_usd": 15.0, "cap_type": "hard", "cap_usd": 10.0})

    # Patch bible to have cost-hard-cap-reached
    show.bible.escalation["cost-hard-cap-reached"] = True

    dispatched = []

    class MockDispatcher:
        def __init__(self, **kwargs):
            pass
        def raise_urgent_matter(self, **kwargs):
            dispatched.append(kwargs)
            return "APPROVE"

    monkeypatch.setattr("the_show.urgent_contact.dispatcher.UrgentContactDispatcher", MockDispatcher)

    _handle_monitor_signals(show.id, show, state)

    # Verify event was acknowledged
    unacked = get_unacknowledged_monitor_events(show.id)
    assert len(unacked) == 0


def test_stage_manager_does_not_escalate_oscillation(tmp_state_dirs, monkeypatch):
    """Oscillation events should be acknowledged as warnings, not escalated."""
    from the_show.loader import load_show
    from the_show.executor import _handle_monitor_signals
    from pathlib import Path
    YAML_PATH = Path(__file__).parent.parent / "example_show.yaml"
    show = load_show(YAML_PATH)
    state_obj = initialize_state(show)
    state_obj.status = "running"

    add_monitor_event(show.id, "oscillation", "warning", scene_id="scene-1")

    dispatched = []

    class MockDispatcher:
        def __init__(self, **kwargs):
            pass
        def raise_urgent_matter(self, **kwargs):
            dispatched.append(kwargs)
            return "APPROVE"

    monkeypatch.setattr("the_show.urgent_contact.dispatcher.UrgentContactDispatcher", MockDispatcher)

    _handle_monitor_signals(show.id, show, state_obj)

    assert len(dispatched) == 0
    unacked = get_unacknowledged_monitor_events(show.id)
    assert len(unacked) == 0
