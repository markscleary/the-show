from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from models import SceneState, ShowSettings, ShowState

STATE_BASE = Path.home() / ".the-show" / "state"

# Scene states that count as "done" for dependency resolution
SUCCESS_STATES: frozenset[str] = frozenset({
    "played-principal",
    "played-fallback-1",
    "played-fallback-2",
    "played-adaptive",
    "played-partial",
})

# All states where a scene will not be re-executed
TERMINAL_STATES: frozenset[str] = frozenset({
    *SUCCESS_STATES,
    "cut",
    "blocked",
    "failed",
    "cascading-dependency-failure",
    "blocked-no-response",
})


def get_db_path(show_id: str) -> Path:
    STATE_BASE.mkdir(parents=True, exist_ok=True)
    return STATE_BASE / f"{show_id}.db"


def _connect(show_id: str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(get_db_path(show_id)))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    return conn


def _connect_path(db_path: str) -> sqlite3.Connection:
    """Connect by explicit path (used by urgent_contact which passes its own db_path)."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS show_state (
            id          INTEGER PRIMARY KEY,
            show_id     TEXT NOT NULL UNIQUE,
            title       TEXT NOT NULL,
            status      TEXT NOT NULL,
            rehearsal   INTEGER DEFAULT 0,
            total_cost_usd REAL DEFAULT 0.0,
            started_at  TEXT,
            updated_at  TEXT,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS scene_state (
            id               INTEGER PRIMARY KEY,
            show_id          TEXT NOT NULL,
            scene_id         TEXT NOT NULL,
            status           TEXT NOT NULL,
            selected_strategy TEXT,
            warnings         TEXT,
            updated_at       TEXT,
            UNIQUE(show_id, scene_id)
        );

        CREATE TABLE IF NOT EXISTS scene_outputs (
            id           INTEGER PRIMARY KEY,
            show_id      TEXT NOT NULL,
            scene_id     TEXT NOT NULL,
            output_name  TEXT NOT NULL,
            output_value TEXT NOT NULL,
            is_trusted   INTEGER DEFAULT 1,
            created_at   TEXT,
            UNIQUE(show_id, scene_id, output_name)
        );

        CREATE TABLE IF NOT EXISTS events (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            show_id        TEXT NOT NULL,
            event_type     TEXT NOT NULL,
            scene_id       TEXT,
            strategy_label TEXT,
            payload        TEXT,
            cost_usd       REAL DEFAULT 0.0,
            duration_ms    INTEGER DEFAULT 0,
            created_at     TEXT
        );

        CREATE TABLE IF NOT EXISTS urgent_matters (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            show_id             TEXT NOT NULL,
            scene_id            TEXT,
            trigger_type        TEXT NOT NULL,
            severity            TEXT NOT NULL,
            prompt              TEXT NOT NULL,
            deadline            TEXT,
            status              TEXT NOT NULL,
            resolution          TEXT,
            resolved_by_channel TEXT,
            resolved_by_contact TEXT,
            created_at          TEXT,
            resolved_at         TEXT
        );

        CREATE TABLE IF NOT EXISTS urgent_sends (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            urgent_matter_id    INTEGER NOT NULL,
            channel_type        TEXT NOT NULL,
            channel_handle      TEXT NOT NULL,
            contact_role        TEXT NOT NULL,
            scheduled_at        TEXT,
            sent_at             TEXT,
            auth_method         TEXT NOT NULL,
            auth_token          TEXT,
            status              TEXT NOT NULL,
            FOREIGN KEY (urgent_matter_id) REFERENCES urgent_matters(id)
        );

        CREATE TABLE IF NOT EXISTS urgent_responses (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            urgent_matter_id    INTEGER NOT NULL,
            send_id             INTEGER,
            raw_response        TEXT NOT NULL,
            authenticated       INTEGER NOT NULL,
            valid_format        INTEGER NOT NULL,
            parsed_action       TEXT,
            received_at         TEXT,
            FOREIGN KEY (urgent_matter_id) REFERENCES urgent_matters(id)
        );

        CREATE INDEX IF NOT EXISTS idx_events_show
            ON events(show_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_scene_state_show
            ON scene_state(show_id);
        CREATE INDEX IF NOT EXISTS idx_urgent_matters_show
            ON urgent_matters(show_id);
    """)


def initialize_state(show: ShowSettings) -> ShowState:
    """Create a fresh DB and return an empty ShowState. Assumes DB does not already exist."""
    conn = _connect(show.id)
    _create_schema(conn)
    now = _now()
    conn.execute(
        """INSERT OR REPLACE INTO show_state
           (show_id, title, status, rehearsal, total_cost_usd, started_at, updated_at)
           VALUES (?, ?, 'planned', ?, 0.0, ?, ?)""",
        (show.id, show.title, 1 if show.rehearsal else 0, now, now),
    )
    for scene in show.running_order:
        conn.execute(
            """INSERT OR IGNORE INTO scene_state
               (show_id, scene_id, status, warnings, updated_at)
               VALUES (?, ?, 'queued', '[]', ?)""",
            (show.id, scene.scene, now),
        )
    conn.commit()
    conn.close()

    state = ShowState(show_id=show.id, title=show.title, status="planned")
    for scene in show.running_order:
        state.scenes[scene.scene] = SceneState(scene=scene.scene)
    return state


def persist_show_state(state: ShowState) -> None:
    """Write show-level state (status, cost) to the DB."""
    now = _now()
    completed_at = now if state.status in {"completed", "aborted"} else None
    conn = _connect(state.show_id)
    conn.execute(
        """UPDATE show_state
           SET status=?, total_cost_usd=?, updated_at=?,
               completed_at=COALESCE(?, completed_at)
           WHERE show_id=?""",
        (state.status, state.total_cost_usd, now, completed_at, state.show_id),
    )
    conn.commit()
    conn.close()


def persist_scene_state(show_id: str, scene_state: SceneState) -> None:
    """Write a single scene's state row."""
    now = _now()
    warnings_json = json.dumps(scene_state.warnings)
    conn = _connect(show_id)
    conn.execute(
        """INSERT INTO scene_state
               (show_id, scene_id, status, selected_strategy, warnings, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(show_id, scene_id) DO UPDATE SET
               status=excluded.status,
               selected_strategy=excluded.selected_strategy,
               warnings=excluded.warnings,
               updated_at=excluded.updated_at""",
        (
            show_id,
            scene_state.scene,
            scene_state.status,
            scene_state.selected_strategy,
            warnings_json,
            now,
        ),
    )
    conn.commit()
    conn.close()


def persist_scene_output(
    show_id: str,
    scene_id: str,
    output_name: str,
    value: Any,
    is_trusted: bool = True,
) -> None:
    """Write (or replace) a scene output value."""
    value_json = json.dumps(value, default=str)
    now = _now()
    conn = _connect(show_id)
    conn.execute(
        """INSERT INTO scene_outputs
               (show_id, scene_id, output_name, output_value, is_trusted, created_at)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(show_id, scene_id, output_name) DO UPDATE SET
               output_value=excluded.output_value,
               is_trusted=excluded.is_trusted""",
        (show_id, scene_id, output_name, value_json, 1 if is_trusted else 0, now),
    )
    conn.commit()
    conn.close()


def persist_state(state: ShowState) -> None:
    """Convenience wrapper: persist show state + all scene states atomically."""
    conn = _connect(state.show_id)
    now = _now()
    completed_at = now if state.status in {"completed", "aborted"} else None
    conn.execute(
        """UPDATE show_state
           SET status=?, total_cost_usd=?, updated_at=?,
               completed_at=COALESCE(?, completed_at)
           WHERE show_id=?""",
        (state.status, state.total_cost_usd, now, completed_at, state.show_id),
    )
    for sc in state.scenes.values():
        conn.execute(
            """INSERT INTO scene_state
                   (show_id, scene_id, status, selected_strategy, warnings, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(show_id, scene_id) DO UPDATE SET
                   status=excluded.status,
                   selected_strategy=excluded.selected_strategy,
                   warnings=excluded.warnings,
                   updated_at=excluded.updated_at""",
            (
                state.show_id,
                sc.scene,
                sc.status,
                sc.selected_strategy,
                json.dumps(sc.warnings),
                now,
            ),
        )
    conn.commit()
    conn.close()


def add_event(
    show_id: str,
    event_type: str,
    scene_id: Optional[str] = None,
    strategy_label: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    cost: float = 0.0,
    duration_ms: int = 0,
) -> None:
    """Append a row to the event log."""
    now = _now()
    payload_json = json.dumps(payload) if payload is not None else None
    conn = _connect(show_id)
    conn.execute(
        """INSERT INTO events
               (show_id, event_type, scene_id, strategy_label, payload,
                cost_usd, duration_ms, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (show_id, event_type, scene_id, strategy_label, payload_json, cost, duration_ms, now),
    )
    conn.commit()
    conn.close()


def load_show_state(show_id: str) -> ShowState:
    """Rebuild ShowState from the database (for resume and programme generation)."""
    if not get_db_path(show_id).exists():
        raise ValueError(f"No state found for show '{show_id}'")
    conn = _connect(show_id)
    row = conn.execute(
        "SELECT * FROM show_state WHERE show_id=?", (show_id,)
    ).fetchone()
    if row is None:
        conn.close()
        raise ValueError(f"No state found for show '{show_id}'")

    state = ShowState(
        show_id=row["show_id"],
        title=row["title"],
        status=row["status"],
        total_cost_usd=row["total_cost_usd"],
    )

    for sc_row in conn.execute(
        "SELECT * FROM scene_state WHERE show_id=?", (show_id,)
    ).fetchall():
        state.scenes[sc_row["scene_id"]] = SceneState(
            scene=sc_row["scene_id"],
            status=sc_row["status"],
            selected_strategy=sc_row["selected_strategy"],
            warnings=json.loads(sc_row["warnings"] or "[]"),
        )

    for out_row in conn.execute(
        "SELECT * FROM scene_outputs WHERE show_id=?", (show_id,)
    ).fetchall():
        value = json.loads(out_row["output_value"])
        state.outputs.setdefault(out_row["scene_id"], {})[out_row["output_name"]] = value

    conn.close()
    return state


def load_scene_outputs(show_id: str) -> Dict[str, Dict[str, Any]]:
    conn = _connect(show_id)
    result: Dict[str, Dict[str, Any]] = {}
    for row in conn.execute(
        "SELECT * FROM scene_outputs WHERE show_id=?", (show_id,)
    ).fetchall():
        result.setdefault(row["scene_id"], {})[row["output_name"]] = json.loads(row["output_value"])
    conn.close()
    return result


def get_events(
    show_id: str,
    since: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    conn = _connect(show_id)
    q = "SELECT * FROM events WHERE show_id=?"
    params: List[Any] = [show_id]
    if since:
        q += " AND created_at >= ?"
        params.append(since)
    q += " ORDER BY created_at"
    if limit:
        q += f" LIMIT {int(limit)}"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "event_type": r["event_type"],
            "scene_id": r["scene_id"],
            "strategy_label": r["strategy_label"],
            "payload": json.loads(r["payload"]) if r["payload"] else None,
            "cost_usd": r["cost_usd"],
            "duration_ms": r["duration_ms"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def show_exists(show_id: str) -> bool:
    return get_db_path(show_id).exists()


def get_show_status(show_id: str) -> Optional[str]:
    """Return status string from DB, or None if not found."""
    if not show_exists(show_id):
        return None
    conn = _connect(show_id)
    row = conn.execute(
        "SELECT status FROM show_state WHERE show_id=?", (show_id,)
    ).fetchone()
    conn.close()
    return row["status"] if row else None


def count_completed_scenes(show_id: str) -> tuple[int, int]:
    """Return (completed, total) scene counts from DB."""
    conn = _connect(show_id)
    rows = conn.execute(
        "SELECT status FROM scene_state WHERE show_id=?", (show_id,)
    ).fetchall()
    conn.close()
    total = len(rows)
    completed = sum(1 for r in rows if r["status"] in TERMINAL_STATES)
    return completed, total


def archive_db(show_id: str) -> Path:
    """Rename the existing DB to <show-id>_<timestamp>.db.abandoned."""
    db_path = get_db_path(show_id)
    if not db_path.exists():
        return db_path
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    abandoned = db_path.parent / f"{show_id}_{ts}.db.abandoned"
    db_path.rename(abandoned)
    return abandoned


# ──────────────────────────────────────────────────────────────────────────────
# Urgent Contact CRUD (called by urgent_contact/dispatcher.py)
# ──────────────────────────────────────────────────────────────────────────────

def create_urgent_matter(
    db_path: str,
    show_id: str,
    scene_id: Optional[str],
    trigger_type: str,
    severity: str,
    prompt: str,
    deadline: Optional[str],
) -> int:
    """Insert a new urgent_matter row; ensure schema exists. Returns matter id."""
    conn = _connect_path(db_path)
    _create_schema(conn)
    now = _now()
    cur = conn.execute(
        """INSERT INTO urgent_matters
               (show_id, scene_id, trigger_type, severity, prompt, deadline, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, 'open', ?)""",
        (show_id, scene_id, trigger_type, severity, prompt, deadline, now),
    )
    matter_id = cur.lastrowid
    conn.commit()
    conn.close()
    return matter_id


def update_urgent_matter(
    db_path: str,
    matter_id: int,
    status: str,
    resolution: Optional[str] = None,
    resolved_by_channel: Optional[str] = None,
    resolved_by_contact: Optional[str] = None,
) -> None:
    now = _now()
    resolved_at = now if status in ("resolved", "exhausted") else None
    conn = _connect_path(db_path)
    conn.execute(
        """UPDATE urgent_matters
           SET status=?, resolution=?, resolved_by_channel=?, resolved_by_contact=?,
               resolved_at=COALESCE(?, resolved_at)
           WHERE id=?""",
        (status, resolution, resolved_by_channel, resolved_by_contact, resolved_at, matter_id),
    )
    conn.commit()
    conn.close()


def create_urgent_send(
    db_path: str,
    matter_id: int,
    channel_type: str,
    channel_handle: str,
    contact_role: str,
    auth_method: str,
    auth_token: Optional[str],
) -> int:
    """Insert a queued send record; returns send id."""
    now = _now()
    conn = _connect_path(db_path)
    cur = conn.execute(
        """INSERT INTO urgent_sends
               (urgent_matter_id, channel_type, channel_handle, contact_role,
                scheduled_at, auth_method, auth_token, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'queued')""",
        (matter_id, channel_type, channel_handle, contact_role, now, auth_method, auth_token),
    )
    send_id = cur.lastrowid
    conn.commit()
    conn.close()
    return send_id


def mark_send_sent(db_path: str, send_id: int) -> None:
    now = _now()
    conn = _connect_path(db_path)
    conn.execute(
        "UPDATE urgent_sends SET status='sent', sent_at=? WHERE id=?",
        (now, send_id),
    )
    conn.commit()
    conn.close()


def cancel_pending_sends(db_path: str, matter_id: int, include_sent: bool = True) -> None:
    """Mark queued (and optionally sent) sends for a matter as cancelled."""
    conn = _connect_path(db_path)
    statuses = "('queued','sent')" if include_sent else "('queued')"
    conn.execute(
        f"UPDATE urgent_sends SET status='cancelled' WHERE urgent_matter_id=? AND status IN {statuses}",
        (matter_id,),
    )
    conn.commit()
    conn.close()


def get_sends_for_matter(db_path: str, matter_id: int) -> List[Dict[str, Any]]:
    conn = _connect_path(db_path)
    rows = conn.execute(
        "SELECT * FROM urgent_sends WHERE urgent_matter_id=? ORDER BY id",
        (matter_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def log_urgent_response(
    db_path: str,
    matter_id: int,
    send_id: Optional[int],
    raw_response: str,
    authenticated: bool,
    valid_format: bool,
    parsed_action: Optional[str],
) -> None:
    now = _now()
    conn = _connect_path(db_path)
    conn.execute(
        """INSERT INTO urgent_responses
               (urgent_matter_id, send_id, raw_response, authenticated, valid_format,
                parsed_action, received_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (matter_id, send_id, raw_response, 1 if authenticated else 0,
         1 if valid_format else 0, parsed_action, now),
    )
    conn.commit()
    conn.close()


def get_urgent_matters(show_id: str) -> List[Dict[str, Any]]:
    """Return all urgent matters for a show (for CLI display)."""
    conn = _connect(show_id)
    rows = conn.execute(
        "SELECT * FROM urgent_matters WHERE show_id=? ORDER BY created_at",
        (show_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_unplanned_urgent_matters(db_path: str, show_id: str) -> int:
    """Count open/resolved urgent matters excluding planned human-approval triggers."""
    conn = _connect_path(db_path)
    row = conn.execute(
        """SELECT COUNT(*) as n FROM urgent_matters
           WHERE show_id=? AND trigger_type != 'human-approval'""",
        (show_id,),
    ).fetchone()
    conn.close()
    return row["n"] if row else 0


def get_send_by_token(db_path: str, auth_token: str) -> Optional[Dict[str, Any]]:
    """Look up a send record by its auth_token (for signed-link click)."""
    conn = _connect_path(db_path)
    row = conn.execute(
        "SELECT * FROM urgent_sends WHERE auth_token=? LIMIT 1",
        (auth_token,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None
