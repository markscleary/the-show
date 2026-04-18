from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


LINK_QUEUE_DB = Path.home() / ".the-show" / "link_queue.db"


def _connect() -> sqlite3.Connection:
    import urgent_contact.link_queue as _m
    db_path = _m.LINK_QUEUE_DB
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS link_responses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            matter_id   INTEGER NOT NULL,
            handle      TEXT NOT NULL,
            action      TEXT NOT NULL,
            token       TEXT NOT NULL,
            received_at TEXT NOT NULL,
            consumed    INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS sms_responses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            from_number TEXT NOT NULL,
            body        TEXT NOT NULL,
            received_at TEXT NOT NULL,
            consumed    INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS whatsapp_responses (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            from_number TEXT NOT NULL,
            body        TEXT NOT NULL,
            received_at TEXT NOT NULL,
            consumed    INTEGER NOT NULL DEFAULT 0
        );
    """)
    conn.commit()
    return conn


def write_link_response(matter_id: int, handle: str, action: str, token: str) -> None:
    conn = _connect()
    conn.execute(
        "INSERT INTO link_responses (matter_id, handle, action, token, received_at) VALUES (?,?,?,?,?)",
        (matter_id, handle, action, token, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def read_link_responses(handle: str) -> List[Dict[str, Any]]:
    """Return unconsumed link responses for handle, marking them consumed atomically."""
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM link_responses WHERE handle=? AND consumed=0 ORDER BY id",
        (handle,),
    ).fetchall()
    if rows:
        placeholders = ",".join("?" * len(rows))
        conn.execute(
            f"UPDATE link_responses SET consumed=1 WHERE id IN ({placeholders})",
            [r["id"] for r in rows],
        )
        conn.commit()
    conn.close()
    return [dict(r) for r in rows]


def write_sms_response(from_number: str, body: str) -> None:
    conn = _connect()
    conn.execute(
        "INSERT INTO sms_responses (from_number, body, received_at) VALUES (?,?,?)",
        (from_number, body, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def read_sms_responses(from_number: str) -> List[Dict[str, Any]]:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM sms_responses WHERE from_number=? AND consumed=0 ORDER BY id",
        (from_number,),
    ).fetchall()
    if rows:
        placeholders = ",".join("?" * len(rows))
        conn.execute(
            f"UPDATE sms_responses SET consumed=1 WHERE id IN ({placeholders})",
            [r["id"] for r in rows],
        )
        conn.commit()
    conn.close()
    return [dict(r) for r in rows]


def write_whatsapp_response(from_number: str, body: str) -> None:
    conn = _connect()
    conn.execute(
        "INSERT INTO whatsapp_responses (from_number, body, received_at) VALUES (?,?,?)",
        (from_number, body, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()


def read_whatsapp_responses(from_number: str) -> List[Dict[str, Any]]:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM whatsapp_responses WHERE from_number=? AND consumed=0 ORDER BY id",
        (from_number,),
    ).fetchall()
    if rows:
        placeholders = ",".join("?" * len(rows))
        conn.execute(
            f"UPDATE whatsapp_responses SET consumed=1 WHERE id IN ({placeholders})",
            [r["id"] for r in rows],
        )
        conn.commit()
    conn.close()
    return [dict(r) for r in rows]
