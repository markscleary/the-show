"""Shared pytest fixtures."""
from __future__ import annotations

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
    return fake_base
