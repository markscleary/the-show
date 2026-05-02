"""v1.1.1 — per-scene channel routing.

Tests the loader/models/dispatcher/executor wiring that lets a scene's
`principal.channels` and `principal.to` filter which contacts in
urgent-contact.contacts receive the urgent matter.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from the_show import state as state_module
from the_show.loader import ValidationError, load_show
from the_show.models import ShowSettings
from the_show.state import (
    get_sends_for_matter,
    get_urgent_matters,
    initialize_state,
)
from the_show.urgent_contact.channels.mock import MockChannel
from the_show.urgent_contact.dispatcher import UrgentContactDispatcher

FAST_POLL = 0.05


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures / helpers
# ──────────────────────────────────────────────────────────────────────────────

def _write_yaml(tmp_path: Path, content: str, name: str = "show.yaml") -> Path:
    p = tmp_path / name
    p.write_text(content)
    return p


def _make_show_with_two_contacts(
    show_id: str = "routing-test",
    mode: str = "parallel",
) -> ShowSettings:
    return ShowSettings(
        id=show_id,
        title="Routing Test",
        urgent_contact={
            "mode": mode,
            "max-per-show": 5,
            "send-interval-seconds": 999,
            "contacts": [
                {"role": "director", "channel": "telegram", "handle": "@dir", "auth": "channel-native"},
                {"role": "tech", "channel": "email", "handle": "tech@example.com", "auth": "channel-native"},
            ],
        },
        running_order=[],
    )


def _make_dispatcher(show: ShowSettings, db_path: str) -> UrgentContactDispatcher:
    # MockChannel handles handles for any "channel_type" only if we register it
    # under that type. We instead expose a single MockChannel and route everything
    # to "mock" for the dispatcher tests by patching contacts to use mock — but for
    # filter tests the channel_type can be telegram/email; the dispatcher.adapters
    # lookup will return None for unknown types, sends stay queued, but matter
    # records and selection are what we assert here.
    return UrgentContactDispatcher(
        db_path=db_path,
        show=show,
        adapters=[MockChannel()],
        poll_interval_seconds=FAST_POLL,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Loader / models — fields parsed onto Strategy
# ──────────────────────────────────────────────────────────────────────────────

_ROUTED_YAML = """
show:
  id: routed-{suffix}
  title: Routed
  urgent-contact:
    mode: parallel
    contacts:
      - role: director
        channel: telegram
        handle: "@dir"
        auth: channel-native
      - role: tech
        channel: email
        handle: "tech@example.com"
        auth: channel-native
  running-order:
    - scene: gate
      title: Gate
      timeout-seconds: 604800
      outputs:
        decision: {{type: string, schema: string}}
      principal:
        method: human-approval
        agent: stage-manager
        brief: "Approve?"
        channels: [telegram]
        to: ["@dir"]
"""


def test_loader_parses_principal_channels(tmp_path):
    p = _write_yaml(tmp_path, _ROUTED_YAML.format(suffix="ch"))
    show = load_show(p)
    gate = show.running_order[0]
    assert gate.principal.channels == ["telegram"]


def test_loader_parses_principal_to(tmp_path):
    p = _write_yaml(tmp_path, _ROUTED_YAML.format(suffix="to"))
    show = load_show(p)
    gate = show.running_order[0]
    assert gate.principal.to == ["@dir"]


def test_loader_defaults_channels_and_to_to_none(tmp_path):
    """Programmes without channels:/to: keep the v1.1.0 default — fanout to all contacts."""
    content = """
show:
  id: default-routing
  title: Default
  running-order:
    - scene: gate
      title: Gate
      timeout-seconds: 604800
      outputs:
        decision: {type: string, schema: string}
      principal:
        method: human-approval
        agent: stage-manager
        brief: "Approve?"
"""
    p = _write_yaml(tmp_path, content)
    show = load_show(p)
    gate = show.running_order[0]
    assert gate.principal.channels is None
    assert gate.principal.to is None


# ──────────────────────────────────────────────────────────────────────────────
# Validate — cross-reference between principal.channels/to and contacts
# ──────────────────────────────────────────────────────────────────────────────

def test_validate_catches_unknown_channel(tmp_path):
    content = """
show:
  id: bad-channel
  title: Bad
  urgent-contact:
    contacts:
      - role: dir
        channel: telegram
        handle: "@dir"
        auth: channel-native
  running-order:
    - scene: gate
      title: Gate
      timeout-seconds: 604800
      outputs:
        decision: {type: string, schema: string}
      principal:
        method: human-approval
        agent: stage-manager
        brief: "Approve?"
        channels: [sms]
"""
    p = _write_yaml(tmp_path, content)
    with pytest.raises(ValidationError, match="sms"):
        load_show(p)


def test_validate_catches_unknown_handle(tmp_path):
    content = """
show:
  id: bad-handle
  title: Bad
  urgent-contact:
    contacts:
      - role: dir
        channel: telegram
        handle: "@dir"
        auth: channel-native
  running-order:
    - scene: gate
      title: Gate
      timeout-seconds: 604800
      outputs:
        decision: {type: string, schema: string}
      principal:
        method: human-approval
        agent: stage-manager
        brief: "Approve?"
        to: ["@somebody-else"]
"""
    p = _write_yaml(tmp_path, content)
    with pytest.raises(ValidationError, match="somebody-else"):
        load_show(p)


def test_validate_accepts_string_to(tmp_path):
    """`to:` accepts a bare string as well as a list — the spec supports both."""
    content = """
show:
  id: string-to
  title: T
  urgent-contact:
    contacts:
      - role: dir
        channel: telegram
        handle: "@dir"
        auth: channel-native
  running-order:
    - scene: gate
      title: Gate
      timeout-seconds: 604800
      outputs:
        decision: {type: string, schema: string}
      principal:
        method: human-approval
        agent: stage-manager
        brief: "Approve?"
        to: "@dir"
"""
    p = _write_yaml(tmp_path, content)
    show = load_show(p)
    assert show.running_order[0].principal.to == "@dir"


def test_validate_passes_for_valid_routing(tmp_path):
    p = _write_yaml(tmp_path, _ROUTED_YAML.format(suffix="ok"))
    show = load_show(p)  # should not raise
    gate = show.running_order[0]
    assert gate.principal.channels == ["telegram"]
    assert gate.principal.to == ["@dir"]


# ──────────────────────────────────────────────────────────────────────────────
# Dispatcher — selection / fanout
# ──────────────────────────────────────────────────────────────────────────────

def test_dispatcher_filters_by_channels(tmp_state_dirs, mock_dirs, monkeypatch):
    """When channels=[telegram] is passed, only the telegram contact gets a send record."""
    show = _make_show_with_two_contacts(show_id="filter-channels")
    initialize_state(ShowSettings(id=show.id, title="T", running_order=[]))
    db_path = str(state_module.STATE_BASE / f"{show.id}.db")

    monkeypatch.setenv("THE_SHOW_URGENT_TIMEOUT", "1")
    dispatcher = _make_dispatcher(show, db_path)
    dispatcher.raise_urgent_matter(
        trigger_type="human-approval",
        severity="urgent",
        prompt="Approve?",
        deadline=None,
        channels=["telegram"],
    )

    matters = get_urgent_matters(show.id)
    sends = get_sends_for_matter(db_path, matters[0]["id"])
    assert len(sends) == 1
    assert sends[0]["channel_type"] == "telegram"
    assert sends[0]["channel_handle"] == "@dir"


def test_dispatcher_filters_by_to(tmp_state_dirs, mock_dirs, monkeypatch):
    """Two contacts on different channels — to filter pins down to one handle."""
    show = ShowSettings(
        id="filter-to",
        title="T",
        urgent_contact={
            "mode": "parallel",
            "contacts": [
                {"role": "a", "channel": "mock", "handle": "@alpha", "auth": "channel-native"},
                {"role": "b", "channel": "mock", "handle": "@beta", "auth": "channel-native"},
            ],
        },
        running_order=[],
    )
    initialize_state(ShowSettings(id=show.id, title="T", running_order=[]))
    db_path = str(state_module.STATE_BASE / f"{show.id}.db")
    monkeypatch.setenv("THE_SHOW_URGENT_TIMEOUT", "1")

    dispatcher = _make_dispatcher(show, db_path)
    dispatcher.raise_urgent_matter(
        trigger_type="human-approval",
        severity="urgent",
        prompt="Approve?",
        deadline=None,
        to=["@beta"],
    )

    matters = get_urgent_matters(show.id)
    sends = get_sends_for_matter(db_path, matters[0]["id"])
    assert len(sends) == 1
    assert sends[0]["channel_handle"] == "@beta"


def test_dispatcher_combined_channels_and_to(tmp_state_dirs, mock_dirs, monkeypatch):
    """channels and to compose with AND semantics."""
    show = ShowSettings(
        id="filter-both",
        title="T",
        urgent_contact={
            "mode": "parallel",
            "contacts": [
                {"role": "a", "channel": "mock", "handle": "@alpha", "auth": "channel-native"},
                {"role": "b", "channel": "mock", "handle": "@beta", "auth": "channel-native"},
                {"role": "c", "channel": "telegram", "handle": "@beta", "auth": "channel-native"},
            ],
        },
        running_order=[],
    )
    initialize_state(ShowSettings(id=show.id, title="T", running_order=[]))
    db_path = str(state_module.STATE_BASE / f"{show.id}.db")
    monkeypatch.setenv("THE_SHOW_URGENT_TIMEOUT", "1")

    dispatcher = _make_dispatcher(show, db_path)
    dispatcher.raise_urgent_matter(
        trigger_type="human-approval",
        severity="urgent",
        prompt="Approve?",
        deadline=None,
        channels=["mock"],
        to=["@beta"],
    )

    matters = get_urgent_matters(show.id)
    sends = get_sends_for_matter(db_path, matters[0]["id"])
    assert len(sends) == 1
    assert sends[0]["channel_type"] == "mock"
    assert sends[0]["channel_handle"] == "@beta"


def test_dispatcher_exhausts_when_no_match(tmp_state_dirs, mock_dirs):
    """Channel filter that matches no contact returns 'exhausted' immediately."""
    show = _make_show_with_two_contacts(show_id="filter-none")
    initialize_state(ShowSettings(id=show.id, title="T", running_order=[]))
    db_path = str(state_module.STATE_BASE / f"{show.id}.db")

    dispatcher = _make_dispatcher(show, db_path)
    result = dispatcher.raise_urgent_matter(
        trigger_type="human-approval",
        severity="urgent",
        prompt="Approve?",
        deadline=None,
        channels=["sms"],  # no contact has SMS
    )
    assert result == "exhausted"
    # No matter record is created when no contact matches — selection happens
    # before the matter row is written, mirroring the "no contacts" early return.
    matters = get_urgent_matters(show.id)
    assert matters == []


def test_dispatcher_default_fanout_unchanged(tmp_state_dirs, mock_dirs, monkeypatch):
    """When channels and to are both None (default), all contacts get send records.

    This is the v1.1.0 behaviour — the fix is backward compatible.
    """
    show = ShowSettings(
        id="default-fanout",
        title="T",
        urgent_contact={
            "mode": "parallel",
            "contacts": [
                {"role": "a", "channel": "mock", "handle": "@a", "auth": "channel-native"},
                {"role": "b", "channel": "mock", "handle": "@b", "auth": "channel-native"},
            ],
        },
        running_order=[],
    )
    initialize_state(ShowSettings(id=show.id, title="T", running_order=[]))
    db_path = str(state_module.STATE_BASE / f"{show.id}.db")
    monkeypatch.setenv("THE_SHOW_URGENT_TIMEOUT", "1")

    dispatcher = _make_dispatcher(show, db_path)
    dispatcher.raise_urgent_matter(
        trigger_type="human-approval",
        severity="urgent",
        prompt="Approve?",
        deadline=None,
        # no channels=, no to= — backward-compatible call signature
    )

    matters = get_urgent_matters(show.id)
    sends = get_sends_for_matter(db_path, matters[0]["id"])
    handles = {s["channel_handle"] for s in sends}
    assert handles == {"@a", "@b"}


# ──────────────────────────────────────────────────────────────────────────────
# Executor — strategy fields forwarded to dispatcher
# ──────────────────────────────────────────────────────────────────────────────

def test_executor_forwards_channels_and_to(tmp_state_dirs, mock_dirs, monkeypatch):
    """run_human_approval normalises strategy.to and forwards both fields."""
    from the_show.executor import run_human_approval
    from the_show.models import (
        AdaptiveConfig,
        CutRule,
        RetryPolicy,
        Scene,
        ShowState,
        SceneState,
        Strategy,
    )

    show = _make_show_with_two_contacts(show_id="exec-forward")
    initialize_state(ShowSettings(id=show.id, title="T", running_order=[]))

    # Capture what raise_urgent_matter sees
    captured: dict = {}

    class FakeDispatcher:
        def __init__(self, *a, **kw):
            pass

        def raise_urgent_matter(self, **kwargs):
            captured.update(kwargs)
            return "APPROVE"

    import the_show.urgent_contact.dispatcher as disp_mod
    monkeypatch.setattr(disp_mod, "UrgentContactDispatcher", FakeDispatcher)
    monkeypatch.setattr(disp_mod, "load_adapters", lambda: {})

    strategy = Strategy(
        method="human-approval",
        agent="stage-manager",
        brief="Approve?",
        severity="urgent",
        channels=["telegram"],
        to="@dir",  # bare string — executor must wrap to list
    )
    scene = Scene(
        scene="gate",
        title="Gate",
        principal=strategy,
        outputs={"decision": {"type": "string"}},
        retry_policy=RetryPolicy(),
        cut=CutRule(),
        adaptive=AdaptiveConfig(),
        timeout_seconds=60,
    )
    state = ShowState(show_id=show.id, title=show.title)
    state.scenes[scene.scene] = SceneState(scene=scene.scene)

    success, _ = run_human_approval(scene, strategy, show, state, "principal")
    assert success is True
    assert captured["channels"] == ["telegram"]
    assert captured["to"] == ["@dir"]  # string normalised to list
    assert captured["scene_id"] == "gate"


# ──────────────────────────────────────────────────────────────────────────────
# Festival heat YAML — validates after the fix lands
# ──────────────────────────────────────────────────────────────────────────────

def test_festival_heat_yaml_loads(tmp_state_dirs, capsys):
    """examples/festival-heat-coordination.yaml validates clean post v1.1.1."""
    yaml_path = Path(__file__).parent.parent / "examples" / "festival-heat-coordination.yaml"
    show = load_show(yaml_path)
    # Director scene routes to telegram, technical scene routes to email
    director = next(s for s in show.running_order if s.scene == "director_approval")
    technical = next(s for s in show.running_order if s.scene == "technical_approval")
    assert director.principal.channels == ["telegram"]
    assert technical.principal.channels == ["email"]
