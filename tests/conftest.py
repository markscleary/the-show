"""Shared pytest fixtures."""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def tmp_state_dirs(tmp_path, monkeypatch):
    """Redirect state and programme output dirs to a temp directory for all tests."""
    import state
    import programme

    fake_base = tmp_path / "the-show" / "state"
    fake_base.mkdir(parents=True)
    monkeypatch.setattr(state, "STATE_BASE", fake_base)
    monkeypatch.setattr(programme, "OUT_BASE", fake_base)

    # Fast dispatcher settings for all tests — prevents 300s hangs on dispatcher polls
    monkeypatch.setenv("THE_SHOW_POLL_INTERVAL", "0.01")
    monkeypatch.setenv("THE_SHOW_MAX_WAIT", "2")

    return fake_base


@pytest.fixture
def mock_dirs(tmp_path, monkeypatch):
    """Redirect MockChannel paths to a temp directory."""
    import urgent_contact.channels.mock as mock_mod

    mock_dir = tmp_path / "urgent-mock"
    mock_dir.mkdir()
    monkeypatch.setattr(mock_mod, "MOCK_DIR", mock_dir)
    monkeypatch.setattr(mock_mod, "SENDS_LOG", mock_dir / "sends.log")
    monkeypatch.setattr(mock_mod, "RESPONSES_FILE", mock_dir / "responses.json")
    return mock_dir


@pytest.fixture
def queue_db(tmp_path, monkeypatch):
    """Redirect link_queue.LINK_QUEUE_DB to a temp file for all channel tests."""
    import urgent_contact.link_queue as lq
    db = tmp_path / "link_queue.db"
    monkeypatch.setattr(lq, "LINK_QUEUE_DB", db)
    return db


@pytest.fixture
def fast_approval(mock_dirs, monkeypatch):
    """Pre-approve the human-approval scene with a known token and fast timing.

    Use this on any test that calls run_show() and expects the show to complete.
    Writes a single APPROVE response entry; seen_keys resets per raise_urgent_matter
    call, so one entry covers multiple run_show() invocations.
    """
    import urgent_contact.dispatcher as dispatcher_mod

    token = "000000"
    # Patch where it's called from (dispatcher imported it at module level)
    monkeypatch.setattr(dispatcher_mod, "generate_reply_token", lambda: token)

    responses_file = mock_dirs / "responses.json"

    def _write():
        time.sleep(0.1)
        entry = {
            "handle": "@producer",
            "text": f"APPROVE {token}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with responses_file.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    threading.Thread(target=_write, daemon=True).start()
    return mock_dirs
