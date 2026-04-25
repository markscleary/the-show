"""Tests for the Urgent Contact machinery (Session 3)."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest

from the_show import state as state_module
from the_show.loader import load_show
from the_show.models import Scene, ShowSettings, Strategy, CutRule, AdaptiveConfig, RetryPolicy
from the_show.state import (
    count_unplanned_urgent_matters,
    create_urgent_matter,
    get_sends_for_matter,
    get_urgent_matters,
    initialize_state,
    log_urgent_response,
)
from the_show.urgent_contact.auth import (
    generate_reply_token,
    generate_signed_token,
    verify_signed_token,
)
from the_show.urgent_contact.channels.mock import MockChannel
from the_show.urgent_contact.degradation import prune_dag_on_blocked
from the_show.urgent_contact.dispatcher import UrgentContactDispatcher
from the_show.urgent_contact.parser import parse_keyword
from the_show.urgent_contact.throttle import UrgentThrottle

YAML_PATH = Path(__file__).parent.parent / "example_show.yaml"

FAST_POLL = 0.05   # test poll interval (seconds)
FAST_TIMEOUT = 1.0  # test deadline (seconds via env)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_dirs(tmp_path, monkeypatch):
    """Redirect MockChannel paths and state to tmp dirs."""
    import the_show.urgent_contact.channels.mock as mock_mod
    mock_dir = tmp_path / "urgent-mock"
    mock_dir.mkdir()
    sends_log = mock_dir / "sends.log"
    responses_file = mock_dir / "responses.json"
    monkeypatch.setattr(mock_mod, "MOCK_DIR", mock_dir)
    monkeypatch.setattr(mock_mod, "SENDS_LOG", sends_log)
    monkeypatch.setattr(mock_mod, "RESPONSES_FILE", responses_file)
    return mock_dir


def _make_show(
    show_id: str = "test-show",
    contacts: list | None = None,
    mode: str = "sequential",
    send_interval: float = 999.0,  # high default so tests control firing
    max_per_show: int = 3,
) -> ShowSettings:
    if contacts is None:
        contacts = [{"role": "producer", "channel": "mock", "handle": "@producer", "auth": "channel-native"}]
    return ShowSettings(
        id=show_id,
        title="Test Show",
        urgent_contact={
            "mode": mode,
            "max-per-show": max_per_show,
            "send-interval-seconds": send_interval,
            "contacts": contacts,
        },
        running_order=[],
    )


def _make_dispatcher(
    show: ShowSettings,
    db_path: str,
    poll_interval: float = FAST_POLL,
) -> UrgentContactDispatcher:
    d = UrgentContactDispatcher(
        db_path=db_path,
        show=show,
        adapters=[MockChannel()],
        poll_interval_seconds=poll_interval,
    )
    return d


def _write_response(mock_dir: Path, handle: str, text: str) -> None:
    resp_file = mock_dir / "responses.json"
    entry = {
        "handle": handle,
        "text": text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    with resp_file.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def _write_response_after_delay(mock_dir: Path, handle: str, text: str, delay: float) -> None:
    def _do():
        time.sleep(delay)
        _write_response(mock_dir, handle, text)
    t = threading.Thread(target=_do, daemon=True)
    t.start()


# ──────────────────────────────────────────────────────────────────────────────
# Parser tests
# ──────────────────────────────────────────────────────────────────────────────

def test_parser_approve():
    assert parse_keyword("APPROVE") == "APPROVE"
    assert parse_keyword("approve") == "APPROVE"
    assert parse_keyword("APPROVE 123456") == "APPROVE"


def test_parser_reject():
    assert parse_keyword("REJECT") == "REJECT"
    assert parse_keyword("reject please") == "REJECT"


def test_parser_stop():
    assert parse_keyword("STOP") == "STOP"


def test_parser_continue():
    assert parse_keyword("CONTINUE") == "CONTINUE"


def test_parser_invalid():
    assert parse_keyword("yes") is None
    assert parse_keyword("I approve of this") is None
    assert parse_keyword("") is None
    assert parse_keyword("Maybe APPROVE?") is None


# ──────────────────────────────────────────────────────────────────────────────
# Auth tests
# ──────────────────────────────────────────────────────────────────────────────

def test_reply_token_is_6_digits():
    token = generate_reply_token()
    assert len(token) == 6
    assert token.isdigit()


def test_signed_token_verifies():
    show_id = "test-show"
    token = generate_signed_token(show_id, matter_id=1, nonce="abc12345")
    assert verify_signed_token(token, show_id)


def test_signed_token_wrong_show_fails():
    token = generate_signed_token("show-a", matter_id=1, nonce="abc12345")
    assert not verify_signed_token(token, "show-b")


def test_signed_token_tampered_fails():
    token = generate_signed_token("test-show", matter_id=1, nonce="abc12345")
    tampered = token[:-4] + "xxxx"
    assert not verify_signed_token(tampered, "test-show")


# ──────────────────────────────────────────────────────────────────────────────
# SQLite record creation
# ──────────────────────────────────────────────────────────────────────────────

def test_raising_creates_matter_record(tmp_state_dirs, mock_dirs, monkeypatch):
    """raise_urgent_matter creates an urgent_matters row and send rows."""
    show = _make_show()
    db_path = str(state_module.STATE_BASE / f"{show.id}.db")
    # Initialise DB schema
    conn_show = ShowSettings(id=show.id, title="Test", running_order=[])
    initialize_state(conn_show)

    # Patch timeout to very short so exhausted returns quickly
    monkeypatch.setenv("THE_SHOW_URGENT_TIMEOUT", "1")

    dispatcher = _make_dispatcher(show, db_path)
    result = dispatcher.raise_urgent_matter(
        trigger_type="human-approval",
        severity="urgent",
        prompt="Do you approve?",
        deadline=None,
        scene_id="test_scene",
    )
    assert result == "exhausted"

    matters = get_urgent_matters(show.id)
    assert len(matters) == 1
    m = matters[0]
    assert m["trigger_type"] == "human-approval"
    assert m["severity"] == "urgent"
    assert m["status"] == "exhausted"
    assert m["scene_id"] == "test_scene"

    sends = get_sends_for_matter(db_path, m["id"])
    assert len(sends) == 1
    assert sends[0]["channel_handle"] == "@producer"
    assert sends[0]["auth_method"] == "channel-native"


def test_raising_creates_send_rows_for_all_contacts(tmp_state_dirs, mock_dirs, monkeypatch):
    show = _make_show(contacts=[
        {"role": "producer", "channel": "mock", "handle": "@producer", "auth": "channel-native"},
        {"role": "director", "channel": "mock", "handle": "@director", "auth": "channel-native"},
    ], mode="parallel")
    initialize_state(ShowSettings(id=show.id, title="T", running_order=[]))
    db_path = str(state_module.STATE_BASE / f"{show.id}.db")

    monkeypatch.setenv("THE_SHOW_URGENT_TIMEOUT", "1")
    dispatcher = _make_dispatcher(show, db_path)
    dispatcher.raise_urgent_matter("human-approval", "urgent", "Approve?", None)

    matters = get_urgent_matters(show.id)
    sends = get_sends_for_matter(db_path, matters[0]["id"])
    assert len(sends) == 2
    handles = {s["channel_handle"] for s in sends}
    assert "@producer" in handles
    assert "@director" in handles


# ──────────────────────────────────────────────────────────────────────────────
# Sequential mode
# ──────────────────────────────────────────────────────────────────────────────

def test_sequential_fires_first_contact_immediately(tmp_state_dirs, mock_dirs, monkeypatch):
    """In sequential mode, the first contact is sent immediately on matter creation."""
    show = _make_show(
        contacts=[
            {"role": "p1", "channel": "mock", "handle": "@p1", "auth": "channel-native"},
            {"role": "p2", "channel": "mock", "handle": "@p2", "auth": "channel-native"},
        ],
        mode="sequential",
        send_interval=999,  # prevent second send
    )
    initialize_state(ShowSettings(id=show.id, title="T", running_order=[]))
    db_path = str(state_module.STATE_BASE / f"{show.id}.db")
    monkeypatch.setenv("THE_SHOW_URGENT_TIMEOUT", "1")

    dispatcher = _make_dispatcher(show, db_path)
    dispatcher.raise_urgent_matter("human-approval", "urgent", "Approve?", None)

    matters = get_urgent_matters(show.id)
    sends = get_sends_for_matter(db_path, matters[0]["id"])
    sent = [s for s in sends if s["status"] == "sent"]
    queued = [s for s in sends if s["status"] in ("queued", "cancelled")]
    assert len(sent) >= 1
    assert sends[0]["channel_handle"] == "@p1"  # first contact fired first
    assert sent[0]["channel_handle"] == "@p1"


def test_sequential_fires_second_after_interval(tmp_state_dirs, mock_dirs, monkeypatch):
    """Second contact fires after send_interval elapses without a response."""
    show = _make_show(
        contacts=[
            {"role": "p1", "channel": "mock", "handle": "@p1", "auth": "channel-native"},
            {"role": "p2", "channel": "mock", "handle": "@p2", "auth": "channel-native"},
        ],
        mode="sequential",
        send_interval=0.2,  # very short interval for test
    )
    initialize_state(ShowSettings(id=show.id, title="T", running_order=[]))
    db_path = str(state_module.STATE_BASE / f"{show.id}.db")
    monkeypatch.setenv("THE_SHOW_URGENT_TIMEOUT", "2")

    dispatcher = _make_dispatcher(show, db_path)
    dispatcher.raise_urgent_matter("human-approval", "urgent", "Approve?", None)

    matters = get_urgent_matters(show.id)
    sends = get_sends_for_matter(db_path, matters[0]["id"])
    sent = [s for s in sends if s["sent_at"] is not None]
    assert len(sent) == 2  # both contacts were fired


# ──────────────────────────────────────────────────────────────────────────────
# Parallel mode
# ──────────────────────────────────────────────────────────────────────────────

def test_parallel_fires_all_contacts(tmp_state_dirs, mock_dirs, monkeypatch):
    """Parallel mode fires all contacts simultaneously on matter creation."""
    show = _make_show(
        contacts=[
            {"role": "p1", "channel": "mock", "handle": "@p1", "auth": "channel-native"},
            {"role": "p2", "channel": "mock", "handle": "@p2", "auth": "channel-native"},
            {"role": "p3", "channel": "mock", "handle": "@p3", "auth": "channel-native"},
        ],
        mode="parallel",
    )
    initialize_state(ShowSettings(id=show.id, title="T", running_order=[]))
    db_path = str(state_module.STATE_BASE / f"{show.id}.db")
    monkeypatch.setenv("THE_SHOW_URGENT_TIMEOUT", "1")

    dispatcher = _make_dispatcher(show, db_path)
    dispatcher.raise_urgent_matter("human-approval", "urgent", "Approve?", None)

    matters = get_urgent_matters(show.id)
    sends = get_sends_for_matter(db_path, matters[0]["id"])
    sent = [s for s in sends if s["sent_at"] is not None]
    assert len(sent) == 3


def test_critical_severity_forces_parallel(tmp_state_dirs, mock_dirs, monkeypatch):
    """Critical severity fires all contacts regardless of mode setting."""
    show = _make_show(
        contacts=[
            {"role": "p1", "channel": "mock", "handle": "@p1", "auth": "channel-native"},
            {"role": "p2", "channel": "mock", "handle": "@p2", "auth": "channel-native"},
        ],
        mode="sequential",
        send_interval=999,
    )
    initialize_state(ShowSettings(id=show.id, title="T", running_order=[]))
    db_path = str(state_module.STATE_BASE / f"{show.id}.db")
    monkeypatch.setenv("THE_SHOW_URGENT_TIMEOUT", "1")

    dispatcher = _make_dispatcher(show, db_path)
    dispatcher.raise_urgent_matter("human-approval", "critical", "CRITICAL: approve?", None)

    matters = get_urgent_matters(show.id)
    sends = get_sends_for_matter(db_path, matters[0]["id"])
    sent = [s for s in sends if s["sent_at"] is not None]
    assert len(sent) == 2  # both fired despite sequential mode


# ──────────────────────────────────────────────────────────────────────────────
# Valid authenticated response resolves and cancels pending sends
# ──────────────────────────────────────────────────────────────────────────────

def test_valid_channel_native_response_resolves(tmp_state_dirs, mock_dirs):
    """An APPROVE response from a channel-native contact resolves the matter."""
    show = _make_show()
    initialize_state(ShowSettings(id=show.id, title="T", running_order=[]))
    db_path = str(state_module.STATE_BASE / f"{show.id}.db")

    # Write response before dispatcher starts; channel-native auth always passes
    _write_response_after_delay(mock_dirs, "@producer", "APPROVE", delay=0.1)

    dispatcher = _make_dispatcher(show, db_path)
    result = dispatcher.raise_urgent_matter("human-approval", "urgent", "Approve?", None)
    assert result == "APPROVE"

    matters = get_urgent_matters(show.id)
    assert matters[0]["status"] == "resolved"
    assert matters[0]["resolution"] == "APPROVE"


def test_reject_response_resolves_with_reject(tmp_state_dirs, mock_dirs):
    show = _make_show()
    initialize_state(ShowSettings(id=show.id, title="T", running_order=[]))
    db_path = str(state_module.STATE_BASE / f"{show.id}.db")

    _write_response_after_delay(mock_dirs, "@producer", "REJECT", delay=0.1)

    dispatcher = _make_dispatcher(show, db_path)
    result = dispatcher.raise_urgent_matter("human-approval", "urgent", "Approve?", None)
    assert result == "REJECT"


def test_continue_response_resolves(tmp_state_dirs, mock_dirs):
    show = _make_show()
    initialize_state(ShowSettings(id=show.id, title="T", running_order=[]))
    db_path = str(state_module.STATE_BASE / f"{show.id}.db")

    _write_response_after_delay(mock_dirs, "@producer", "CONTINUE", delay=0.1)

    dispatcher = _make_dispatcher(show, db_path)
    result = dispatcher.raise_urgent_matter("human-approval", "urgent", "Approve?", None)
    assert result == "CONTINUE"


def test_resolution_cancels_pending_sends(tmp_state_dirs, mock_dirs):
    """When one contact responds, remaining queued sends are cancelled."""
    show = _make_show(
        contacts=[
            {"role": "p1", "channel": "mock", "handle": "@p1", "auth": "channel-native"},
            {"role": "p2", "channel": "mock", "handle": "@p2", "auth": "channel-native"},
        ],
        mode="sequential",
        send_interval=999,  # p2 never fires
    )
    initialize_state(ShowSettings(id=show.id, title="T", running_order=[]))
    db_path = str(state_module.STATE_BASE / f"{show.id}.db")

    _write_response_after_delay(mock_dirs, "@p1", "APPROVE", delay=0.1)

    dispatcher = _make_dispatcher(show, db_path)
    result = dispatcher.raise_urgent_matter("human-approval", "urgent", "Approve?", None)
    assert result == "APPROVE"

    matters = get_urgent_matters(show.id)
    sends = get_sends_for_matter(db_path, matters[0]["id"])
    cancelled = [s for s in sends if s["status"] == "cancelled"]
    assert len(cancelled) >= 1  # the queued p2 send is cancelled


# ──────────────────────────────────────────────────────────────────────────────
# Reply-token auth
# ──────────────────────────────────────────────────────────────────────────────

def test_reply_token_auth_passes_with_token(tmp_state_dirs, mock_dirs, monkeypatch):
    """A response containing the reply token is authenticated."""
    show = _make_show(contacts=[
        {"role": "op", "channel": "mock", "handle": "@op", "auth": "reply-token"},
    ])
    initialize_state(ShowSettings(id=show.id, title="T", running_order=[]))
    db_path = str(state_module.STATE_BASE / f"{show.id}.db")

    # Patch at the dispatcher's import site so the local reference is updated.
    import the_show.urgent_contact.dispatcher as disp_mod
    monkeypatch.setattr(disp_mod, "generate_reply_token", lambda: "999999")

    _write_response_after_delay(mock_dirs, "@op", "APPROVE 999999", delay=0.1)

    dispatcher = _make_dispatcher(show, db_path)
    result = dispatcher.raise_urgent_matter("human-approval", "urgent", "Approve?", None)
    assert result == "APPROVE"


def test_unauthenticated_reply_token_dropped(tmp_state_dirs, mock_dirs, monkeypatch):
    """A response without the token is silently dropped; timer continues."""
    show = _make_show(contacts=[
        {"role": "op", "channel": "mock", "handle": "@op", "auth": "reply-token"},
    ])
    initialize_state(ShowSettings(id=show.id, title="T", running_order=[]))
    db_path = str(state_module.STATE_BASE / f"{show.id}.db")

    # Force token to a known value (patch at dispatcher's import site)
    import the_show.urgent_contact.dispatcher as disp_mod
    monkeypatch.setattr(disp_mod, "generate_reply_token", lambda: "111111")

    # Write a response WITHOUT the token — should be dropped
    _write_response_after_delay(mock_dirs, "@op", "APPROVE", delay=0.1)

    monkeypatch.setenv("THE_SHOW_URGENT_TIMEOUT", "1")
    dispatcher = _make_dispatcher(show, db_path)
    result = dispatcher.raise_urgent_matter("human-approval", "urgent", "Approve?", None)
    # Timer should exhaust because the response without token is dropped
    assert result == "exhausted"

    # Check urgent_responses has an unauthenticated record
    matters = get_urgent_matters(show.id)
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM urgent_responses WHERE urgent_matter_id=?", (matters[0]["id"],)
    ).fetchall()
    conn.close()
    unauthed = [r for r in rows if not r["authenticated"]]
    assert len(unauthed) >= 1


# ──────────────────────────────────────────────────────────────────────────────
# Invalid format response
# ──────────────────────────────────────────────────────────────────────────────

def test_invalid_format_does_not_resolve(tmp_state_dirs, mock_dirs, monkeypatch):
    """Free-text response doesn't resolve; timer continues to exhaustion."""
    show = _make_show()
    initialize_state(ShowSettings(id=show.id, title="T", running_order=[]))
    db_path = str(state_module.STATE_BASE / f"{show.id}.db")

    _write_response_after_delay(mock_dirs, "@producer", "yes I think so", delay=0.1)

    monkeypatch.setenv("THE_SHOW_URGENT_TIMEOUT", "1")
    dispatcher = _make_dispatcher(show, db_path)
    result = dispatcher.raise_urgent_matter("human-approval", "urgent", "Approve?", None)
    assert result == "exhausted"

    # Check urgent_responses has a valid_format=False record
    matters = get_urgent_matters(show.id)
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM urgent_responses WHERE urgent_matter_id=?", (matters[0]["id"],)
    ).fetchall()
    conn.close()
    invalid = [r for r in rows if r["authenticated"] and not r["valid_format"]]
    assert len(invalid) >= 1


# ──────────────────────────────────────────────────────────────────────────────
# Exhaustion
# ──────────────────────────────────────────────────────────────────────────────

def test_exhaustion_when_no_response(tmp_state_dirs, mock_dirs, monkeypatch):
    """Matter exhausts when deadline passes with no response."""
    show = _make_show()
    initialize_state(ShowSettings(id=show.id, title="T", running_order=[]))
    db_path = str(state_module.STATE_BASE / f"{show.id}.db")

    monkeypatch.setenv("THE_SHOW_URGENT_TIMEOUT", "1")
    dispatcher = _make_dispatcher(show, db_path)
    result = dispatcher.raise_urgent_matter("human-approval", "urgent", "Approve?", None)
    assert result == "exhausted"

    matters = get_urgent_matters(show.id)
    assert matters[0]["status"] == "exhausted"


def test_exhaustion_returns_exhausted_string(tmp_state_dirs, mock_dirs, monkeypatch):
    """The return value is the string 'exhausted', not None or an exception."""
    show = _make_show()
    initialize_state(ShowSettings(id=show.id, title="T", running_order=[]))
    db_path = str(state_module.STATE_BASE / f"{show.id}.db")

    monkeypatch.setenv("THE_SHOW_URGENT_TIMEOUT", "1")
    dispatcher = _make_dispatcher(show, db_path)
    result = dispatcher.raise_urgent_matter("human-approval", "urgent", "Approve?", None)
    assert isinstance(result, str)
    assert result == "exhausted"


def test_max_wait_caps_explicit_deadline(tmp_state_dirs, mock_dirs, monkeypatch):
    """THE_SHOW_MAX_WAIT caps the deadline even when an explicit deadline was provided.

    This is intentional: THE_SHOW_MAX_WAIT is a hard ceiling for test environments.
    In production it is never set, so it has no effect. When it IS set, it overrides
    even YAML-declared timeout-seconds so tests do not wait minutes for approval gates.

    Previously the cap was only applied on the deadline=None path, which caused the
    exhausted/blocked-no-response executor tests to hang indefinitely because
    run_human_approval always passes an explicit deadline derived from scene.timeout_seconds.
    """
    import time as _time
    from datetime import datetime, timedelta, timezone

    show = _make_show()
    initialize_state(ShowSettings(id=show.id, title="T", running_order=[]))
    db_path = str(state_module.STATE_BASE / f"{show.id}.db")

    # THE_SHOW_MAX_WAIT=0.3s caps the wait to 300 ms.
    monkeypatch.setenv("THE_SHOW_MAX_WAIT", "0.3")
    monkeypatch.setenv("THE_SHOW_POLL_INTERVAL", "0.05")

    # Explicit deadline ~10 seconds from now (simulates YAML timeout-seconds: 10)
    explicit_deadline = (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat()

    start = _time.time()
    dispatcher = _make_dispatcher(show, db_path)
    result = dispatcher.raise_urgent_matter("human-approval", "urgent", "Approve?", explicit_deadline)
    elapsed = _time.time() - start

    assert result == "exhausted"
    # Must have waited ~0.3s (the max_wait cap), not the full 10s explicit deadline.
    assert elapsed < 2.0, (
        f"THE_SHOW_MAX_WAIT did not cap the explicit deadline — elapsed {elapsed:.2f}s"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Throttle
# ──────────────────────────────────────────────────────────────────────────────

def test_throttle_blocks_after_limit(tmp_state_dirs, mock_dirs):
    """Urgent matters are suppressed after reaching max-per-show."""
    show = _make_show(max_per_show=2)
    db = ShowSettings(id=show.id, title="T", running_order=[])
    initialize_state(db)
    db_path = str(state_module.STATE_BASE / f"{show.id}.db")

    # Manually insert 2 unplanned matters
    for i in range(2):
        create_urgent_matter(
            db_path, show.id, None, "monitor-triggered", "urgent", "auto", None
        )

    throttle = UrgentThrottle(db_path, show.id, max_per_show=2)
    assert not throttle.is_allowed("urgent", "monitor-triggered")


def test_throttle_allows_planned_human_approval(tmp_state_dirs, mock_dirs):
    """Planned human-approval scenes are always exempt from throttle."""
    show = _make_show(max_per_show=0)
    db = ShowSettings(id=show.id, title="T", running_order=[])
    initialize_state(db)
    db_path = str(state_module.STATE_BASE / f"{show.id}.db")

    throttle = UrgentThrottle(db_path, show.id, max_per_show=0)
    assert throttle.is_allowed("urgent", "human-approval")


def test_throttle_allows_critical_always(tmp_state_dirs, mock_dirs):
    """Critical severity bypasses throttle regardless of count."""
    show = _make_show(max_per_show=0)
    db = ShowSettings(id=show.id, title="T", running_order=[])
    initialize_state(db)
    db_path = str(state_module.STATE_BASE / f"{show.id}.db")

    # Saturate throttle with unplanned matters
    for i in range(5):
        create_urgent_matter(
            db_path, show.id, None, "monitor-triggered", "urgent", "auto", None
        )

    throttle = UrgentThrottle(db_path, show.id, max_per_show=0)
    assert throttle.is_allowed("critical", "monitor-triggered")


def test_dispatcher_returns_throttled_when_exceeded(tmp_state_dirs, mock_dirs):
    """Dispatcher returns 'throttled' when throttle denies the matter."""
    show = _make_show(max_per_show=1)
    db = ShowSettings(id=show.id, title="T", running_order=[])
    initialize_state(db)
    db_path = str(state_module.STATE_BASE / f"{show.id}.db")

    # Use up the single unplanned slot
    create_urgent_matter(
        db_path, show.id, None, "monitor-triggered", "urgent", "auto", None
    )

    dispatcher = _make_dispatcher(show, db_path)
    result = dispatcher.raise_urgent_matter(
        trigger_type="monitor-triggered",  # unplanned — counts toward throttle
        severity="urgent",
        prompt="Should we continue?",
        deadline=None,
    )
    assert result == "throttled"


# ──────────────────────────────────────────────────────────────────────────────
# DAG pruning
# ──────────────────────────────────────────────────────────────────────────────

def _make_linear_show(show_id: str = "dag-show") -> ShowSettings:
    """A→B→C dependency chain for DAG pruning tests."""
    def _scene(scene_id, deps):
        return Scene(
            scene=scene_id,
            title=scene_id,
            principal=Strategy(method="sub-agent", agent="deep-dive"),
            outputs={"out": {"type": "string"}},
            depends_on=deps,
        )
    return ShowSettings(
        id=show_id,
        title="DAG Test",
        running_order=[
            _scene("scene_a", []),
            _scene("scene_b", ["scene_a"]),
            _scene("scene_c", ["scene_b"]),
        ],
    )


def test_dag_pruning_marks_direct_dependent(tmp_state_dirs):
    show = _make_linear_show()
    state = initialize_state(show)
    state.status = "running"

    # scene_a is blocked-no-response; prune from there
    state.scenes["scene_a"].status = "blocked-no-response"

    affected = prune_dag_on_blocked(state, show, "scene_a")
    assert "scene_b" in affected
    assert state.scenes["scene_b"].status == "cascading-dependency-failure"


def test_dag_pruning_marks_transitive_dependents(tmp_state_dirs):
    show = _make_linear_show()
    state = initialize_state(show)
    state.status = "running"

    state.scenes["scene_a"].status = "blocked-no-response"
    affected = prune_dag_on_blocked(state, show, "scene_a")

    assert "scene_b" in affected
    assert "scene_c" in affected
    assert state.scenes["scene_c"].status == "cascading-dependency-failure"


def test_dag_pruning_skips_already_terminal(tmp_state_dirs):
    show = _make_linear_show()
    state = initialize_state(show)
    state.status = "running"

    state.scenes["scene_a"].status = "blocked-no-response"
    state.scenes["scene_b"].status = "played-principal"  # already terminal

    affected = prune_dag_on_blocked(state, show, "scene_a")
    # scene_b is terminal — skip it, but scene_c still depends on scene_b only
    assert "scene_b" not in affected
    # scene_c is NOT affected because scene_b was already terminal (skipped in BFS)
    assert "scene_c" not in affected


def test_dag_pruning_returns_empty_for_leaf(tmp_state_dirs):
    show = _make_linear_show()
    state = initialize_state(show)
    # scene_c is a leaf — nothing depends on it
    affected = prune_dag_on_blocked(state, show, "scene_c")
    assert affected == []


# ──────────────────────────────────────────────────────────────────────────────
# End-to-end executor integration
# ──────────────────────────────────────────────────────────────────────────────

def test_executor_human_approval_resolves_approve(tmp_state_dirs, mock_dirs, monkeypatch):
    """When the operator responds APPROVE, the show continues past the human-approval scene."""
    from the_show.executor import run_show

    # Patch at the dispatcher's import site so the local reference is updated.
    import the_show.urgent_contact.dispatcher as disp_mod
    monkeypatch.setattr(disp_mod, "generate_reply_token", lambda: "777777")
    monkeypatch.setenv("THE_SHOW_POLL_INTERVAL", "0.05")

    # Write APPROVE response into mock file with token
    _write_response_after_delay(mock_dirs, "@producer", "APPROVE 777777", delay=0.15)

    show = load_show(YAML_PATH)
    result = run_show(show)

    # The show should complete (approval came through)
    assert result.status == "completed"
    # approve_run should be played-principal (APPROVE returned from dispatcher)
    assert result.scenes["approve_run"].status == "played-principal"


def test_executor_exhausted_sets_blocked_no_response(tmp_state_dirs, mock_dirs, monkeypatch):
    """When no response arrives, approve_run becomes blocked-no-response."""
    from the_show.executor import run_show

    monkeypatch.setenv("THE_SHOW_URGENT_TIMEOUT", "1")
    monkeypatch.setenv("THE_SHOW_POLL_INTERVAL", "0.1")
    # Cap the wall-clock wait regardless of scene.timeout_seconds (approve_run defaults to
    # 7 days since commit 69df7e8; THE_SHOW_MAX_WAIT overrides the scene-level deadline).
    monkeypatch.setenv("THE_SHOW_MAX_WAIT", "1")

    show = load_show(YAML_PATH)
    result = run_show(show)

    assert result.scenes["approve_run"].status == "blocked-no-response"


def test_executor_blocked_no_response_triggers_dag_pruning(tmp_state_dirs, mock_dirs, monkeypatch):
    """blocked-no-response on approve_run cascades to scenes that depend on it."""
    from the_show.executor import run_show

    monkeypatch.setenv("THE_SHOW_URGENT_TIMEOUT", "1")
    monkeypatch.setenv("THE_SHOW_POLL_INTERVAL", "0.1")
    monkeypatch.setenv("THE_SHOW_MAX_WAIT", "1")

    show = load_show(YAML_PATH)
    result = run_show(show)

    # enrich_contacts depends on [load_targets, approve_run]
    # Since approve_run is blocked-no-response, enrich_contacts should cascade
    assert result.scenes["enrich_contacts"].status == "cascading-dependency-failure"


def test_stub_not_present_in_executor():
    """Verify the Session 2 stub function has been removed from executor.py."""
    from the_show import executor
    assert not hasattr(executor, "stub_urgent_contact_approval"), (
        "stub_urgent_contact_approval should have been removed in Session 3"
    )


def test_urgent_contact_resolved_event_logged(tmp_state_dirs, mock_dirs, monkeypatch):
    """The executor logs an urgent_contact_resolved event (not the old stub event)."""
    from the_show.executor import run_show
    # Patch at the dispatcher's import site (direct import — auth_mod patch won't reach it)
    import the_show.urgent_contact.dispatcher as disp_mod
    monkeypatch.setattr(disp_mod, "generate_reply_token", lambda: "888888")
    monkeypatch.setenv("THE_SHOW_POLL_INTERVAL", "0.05")

    _write_response_after_delay(mock_dirs, "@producer", "APPROVE 888888", delay=0.15)

    show = load_show(YAML_PATH)
    run_show(show)

    events = state_module.get_events(show.id)
    event_types = [ev["event_type"] for ev in events]
    assert "urgent_contact_resolved" in event_types
    assert "urgent_contact_stubbed" not in event_types
    # Ensure it was actually an APPROVE (not just an exhaustion)
    resolved_events = [ev for ev in events if ev["event_type"] == "urgent_contact_resolved"]
    assert resolved_events[0]["payload"]["resolution"] == "APPROVE"
