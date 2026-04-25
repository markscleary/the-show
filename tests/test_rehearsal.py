"""Tests for rehearsal mode — dry-run programmes without burning tokens or channels."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from the_show import state as state_mod
from the_show.executor import run_show
from the_show.models import (
    AdaptiveConfig,
    Bible,
    CutRule,
    RetryPolicy,
    Scene,
    ShowSettings,
    Strategy,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _sub_agent_scene(scene_id: str, depends_on: list | None = None) -> Scene:
    return Scene(
        scene=scene_id,
        title=f"Scene {scene_id}",
        principal=Strategy(
            method="sub-agent",
            agent="test",
            brief="Return test data",
            params={"model": "test-model"},
        ),
        outputs={f"{scene_id}_result": {"type": "dict"}},
        success_when={"schema": "dict"},
        depends_on=depends_on or [],
    )


def _approval_scene(scene_id: str, depends_on: list | None = None) -> Scene:
    return Scene(
        scene=scene_id,
        title="Approval required",
        principal=Strategy(
            method="human-approval",
            agent="test",
            brief="Please approve to continue",
            severity="urgent",
        ),
        outputs={f"{scene_id}_result": {"type": "string"}},
        depends_on=depends_on or [],
    )


def _make_show(
    show_id: str,
    scenes: list,
    rehearsal: bool = True,
) -> ShowSettings:
    return ShowSettings(
        id=show_id,
        title="Rehearsal test show",
        rehearsal=rehearsal,
        urgent_contact={
            "mode": "sequential",
            "max-per-show": 5,
            "send-interval-seconds": 1,
            "contacts": [
                {"role": "operator", "channel": "mock", "handle": "@test", "auth": "channel-native"}
            ],
        },
        running_order=scenes,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_rehearsal_programme_runs_to_completion(tmp_state_dirs, monkeypatch):
    """Rehearsal mode runs a full programme to completed status with all scenes played."""
    from the_show import rehearsal_adapter
    monkeypatch.setattr(rehearsal_adapter, "REHEARSAL_DIR", tmp_state_dirs / "rehearsal")

    show = _make_show(
        "rehearsal-basic",
        [_sub_agent_scene("scene_a"), _sub_agent_scene("scene_b")],
    )
    result = run_show(show)

    assert result.status == "completed"
    for scene_id, sc in result.scenes.items():
        assert sc.status in state_mod.SUCCESS_STATES, f"{scene_id}: {sc.status}"


def test_rehearsal_no_real_llm_calls(tmp_state_dirs, monkeypatch):
    """In rehearsal mode, call_sub_agent is never invoked."""
    from the_show import adapters
    from the_show import rehearsal_adapter
    monkeypatch.setattr(rehearsal_adapter, "REHEARSAL_DIR", tmp_state_dirs / "rehearsal")

    called = []

    def _tracking_sub_agent(model: str, prompt: str, max_tokens: int = 2000):
        called.append({"model": model})
        return {"text": "real call made"}

    monkeypatch.setattr(adapters, "call_sub_agent", _tracking_sub_agent)

    show = _make_show("rehearsal-no-llm", [_sub_agent_scene("scene_a")])
    run_show(show)

    assert called == [], f"call_sub_agent was invoked {len(called)} time(s) in rehearsal mode"


def test_rehearsal_no_real_channel_sends(tmp_state_dirs, monkeypatch):
    """In rehearsal mode, UrgentContactDispatcher.raise_urgent_matter is never called."""
    from the_show import rehearsal_adapter
    import the_show.urgent_contact.dispatcher as disp_mod
    monkeypatch.setattr(rehearsal_adapter, "REHEARSAL_DIR", tmp_state_dirs / "rehearsal")

    dispatch_calls = []
    original_raise = disp_mod.UrgentContactDispatcher.raise_urgent_matter

    def _tracking_raise(self, *args, **kwargs):
        dispatch_calls.append(kwargs.get("trigger_type", args[0] if args else "unknown"))
        return original_raise(self, *args, **kwargs)

    monkeypatch.setattr(disp_mod.UrgentContactDispatcher, "raise_urgent_matter", _tracking_raise)

    show = _make_show(
        "rehearsal-no-sends",
        [_sub_agent_scene("scene_a"), _approval_scene("approve_a", depends_on=["scene_a"])],
    )
    run_show(show)

    assert dispatch_calls == [], (
        f"UrgentContactDispatcher.raise_urgent_matter was called {len(dispatch_calls)} time(s) "
        f"in rehearsal mode: {dispatch_calls}"
    )


def test_rehearsal_urgent_contact_logged_to_file(tmp_state_dirs, monkeypatch):
    """In rehearsal mode, urgent-contact events are logged to the rehearsal log file."""
    from the_show import rehearsal_adapter
    rehearsal_dir = tmp_state_dirs / "rehearsal"
    monkeypatch.setattr(rehearsal_adapter, "REHEARSAL_DIR", rehearsal_dir)
    monkeypatch.delenv("SHOW_REHEARSAL_APPROVAL", raising=False)

    show = _make_show(
        "rehearsal-log-test",
        [_sub_agent_scene("scene_a"), _approval_scene("approve_a", depends_on=["scene_a"])],
    )
    run_show(show)

    log_file = rehearsal_dir / show.id / "urgent_contact.log"
    assert log_file.exists(), f"Rehearsal urgent-contact log not found at {log_file}"
    entries = [json.loads(line) for line in log_file.read_text().splitlines() if line.strip()]
    assert len(entries) >= 1
    assert entries[0]["type"] == "urgent_contact"
    assert entries[0]["scene_id"] == "approve_a"
    assert entries[0]["synthetic_resolution"] == "APPROVE"


def test_rehearsal_approval_resolves_synthetically(tmp_state_dirs, monkeypatch):
    """In rehearsal mode, approval-wait resolves immediately with APPROVE by default."""
    from the_show import rehearsal_adapter
    monkeypatch.setattr(rehearsal_adapter, "REHEARSAL_DIR", tmp_state_dirs / "rehearsal")
    monkeypatch.delenv("SHOW_REHEARSAL_APPROVAL", raising=False)

    show = _make_show(
        "rehearsal-approve",
        [_sub_agent_scene("scene_a"), _approval_scene("approve_a", depends_on=["scene_a"])],
    )
    result = run_show(show)

    events = state_mod.get_events(show.id)
    resolved = [ev for ev in events if ev["event_type"] == "urgent_contact_resolved"]
    assert len(resolved) >= 1, "Expected urgent_contact_resolved event"
    assert resolved[0]["payload"]["resolution"] == "APPROVE"
    assert resolved[0]["payload"].get("rehearsal") is True

    assert result.scenes["approve_a"].status in state_mod.SUCCESS_STATES


def test_rehearsal_failure_injection(tmp_state_dirs, monkeypatch):
    """SHOW_REHEARSAL_APPROVAL=REJECT causes approval scenes to fail."""
    from the_show import rehearsal_adapter
    monkeypatch.setattr(rehearsal_adapter, "REHEARSAL_DIR", tmp_state_dirs / "rehearsal")
    monkeypatch.setenv("SHOW_REHEARSAL_APPROVAL", "REJECT")

    show = _make_show(
        "rehearsal-reject",
        [_sub_agent_scene("scene_a"), _approval_scene("approve_a", depends_on=["scene_a"])],
    )
    result = run_show(show)

    approval_sc = result.scenes.get("approve_a")
    assert approval_sc is not None
    assert approval_sc.status not in state_mod.SUCCESS_STATES, (
        f"Approval scene should have failed on REJECT but got status: {approval_sc.status}"
    )

    events = state_mod.get_events(show.id)
    resolved = [ev for ev in events if ev["event_type"] == "urgent_contact_resolved"]
    assert len(resolved) >= 1
    assert resolved[0]["payload"]["resolution"] == "REJECT"
