"""Tests for SQLAlchemy Core + Alembic migration infrastructure (scene 1 of v1.0 build)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _run_migration(db_path: str) -> None:
    """Apply Alembic migrations to a DB path."""
    import os
    import subprocess
    import sys

    env = {**os.environ, "THE_SHOW_ALEMBIC_DB_URL": f"sqlite:///{db_path}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(Path(__file__).parent.parent),
    )
    assert result.returncode == 0, (
        f"alembic upgrade head failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )


def _alembic_current(db_path: str) -> str:
    """Return the current Alembic revision for a DB."""
    import os
    import subprocess
    import sys

    env = {**os.environ, "THE_SHOW_ALEMBIC_DB_URL": f"sqlite:///{db_path}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(Path(__file__).parent.parent),
    )
    return result.stdout


def test_migration_runs_without_error_on_fresh_db(tmp_path):
    """Alembic upgrade head on a fresh SQLite DB completes without error."""
    db_path = str(tmp_path / "fresh.db")
    _run_migration(db_path)

    conn = sqlite3.connect(db_path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    conn.close()

    expected_new_tables = {
        "signed_tokens", "retries", "costs",
        "adapter_invocations", "schema_validations", "delivery_artefacts",
        "alembic_version",
    }
    assert expected_new_tables <= tables, (
        f"Expected new tables not all present. Missing: {expected_new_tables - tables}"
    )


def test_migration_is_idempotent(tmp_path):
    """Running alembic upgrade head twice does not raise an error."""
    db_path = str(tmp_path / "idempotent.db")
    _run_migration(db_path)
    _run_migration(db_path)  # second run should be a no-op

    # Should still be at head
    current = _alembic_current(db_path)
    assert "0001" in current


def test_existing_state_functions_still_work_after_migration(tmp_path, monkeypatch):
    """Existing state.py functions work correctly on a DB that has had migrations applied."""
    import state as state_mod
    from models import Scene, ShowSettings, Strategy

    db_dir = tmp_path / "state"
    db_dir.mkdir()
    monkeypatch.setattr(state_mod, "STATE_BASE", db_dir)

    show = ShowSettings(
        id="migration-compat-test",
        title="Migration compatibility test",
        running_order=[
            Scene(
                scene="scene_1",
                title="Test scene",
                principal=Strategy(method="tool-call", agent="test", action="read-csv",
                                   params={"path": "/tmp/fake.csv"}),
                outputs={"out": {"type": "list"}},
            )
        ],
    )

    # Initialize state (creates the DB with state.py schema)
    show_state = state_mod.initialize_state(show)
    db_path = str(state_mod.get_db_path(show.id))

    # Apply migrations on top
    _run_migration(db_path)

    # state.py functions should still work
    show_state.status = "running"
    show_state.total_cost_usd = 0.05
    state_mod.persist_show_state(show_state)

    loaded = state_mod.load_show_state(show.id)
    assert loaded.status == "running"
    assert loaded.total_cost_usd == pytest.approx(0.05)


def test_alembic_current_reports_correct_revision(tmp_path):
    """After migration, alembic current reports revision 0001 (head)."""
    db_path = str(tmp_path / "revision-check.db")
    _run_migration(db_path)

    current_output = _alembic_current(db_path)
    assert "0001" in current_output, (
        f"Expected '0001' in alembic current output, got: {current_output!r}"
    )
