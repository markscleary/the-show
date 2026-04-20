"""SQLAlchemy Core metadata definitions for The Show.

Additive layer — the existing sqlite3 calls in state.py remain untouched.
These definitions map the conceptual v1.0 schema (11 tables) onto the physical
SQLite databases used per show.

Conceptual → physical mapping:
  programmes         → show_state
  scenes             → scene_state
  runs               → events (event_type='attempt')
  urgent_contacts    → urgent_matters
  responses          → urgent_responses
  (new) signed_tokens, retries, costs, adapter_invocations,
        schema_validations, delivery_artefacts
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
)

metadata = MetaData()

# ── Existing tables (defined here for reference — managed by state.py) ─────

programmes = Table(
    "show_state",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("show_id", String, nullable=False, unique=True),
    Column("title", String, nullable=False),
    Column("status", String, nullable=False),
    Column("rehearsal", Integer, default=0),
    Column("total_cost_usd", Float, default=0.0),
    Column("started_at", String),
    Column("updated_at", String),
    Column("completed_at", String),
)

scenes = Table(
    "scene_state",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("show_id", String, nullable=False),
    Column("scene_id", String, nullable=False),
    Column("status", String, nullable=False),
    Column("selected_strategy", String),
    Column("warnings", Text),
    Column("updated_at", String),
)

urgent_contacts = Table(
    "urgent_matters",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("show_id", String, nullable=False),
    Column("scene_id", String),
    Column("trigger_type", String, nullable=False),
    Column("severity", String, nullable=False),
    Column("prompt", Text, nullable=False),
    Column("deadline", String),
    Column("status", String, nullable=False),
    Column("resolution", String),
    Column("resolved_by_channel", String),
    Column("resolved_by_contact", String),
    Column("created_at", String),
    Column("resolved_at", String),
)

responses = Table(
    "urgent_responses",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("urgent_matter_id", Integer, ForeignKey("urgent_matters.id")),
    Column("send_id", Integer),
    Column("raw_response", Text, nullable=False),
    Column("authenticated", Integer, nullable=False),
    Column("valid_format", Integer, nullable=False),
    Column("parsed_action", String),
    Column("received_at", String),
)

# ── New v1.0 tables ──────────────────────────────────────────────────────────

signed_tokens = Table(
    "signed_tokens",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("show_id", String, nullable=False),
    Column("token", String, nullable=False, unique=True),
    Column("purpose", String, nullable=False),  # reply-token | signed-link
    Column("matter_id", Integer),
    Column("used", Integer, default=0),
    Column("created_at", String),
    Column("expires_at", String),
)

retries = Table(
    "retries",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("show_id", String, nullable=False),
    Column("scene_id", String, nullable=False),
    Column("strategy_label", String),
    Column("attempt_number", Integer, nullable=False),
    Column("error_type", String),
    Column("error_message", Text),
    Column("retried_at", String),
)

costs = Table(
    "costs",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("show_id", String, nullable=False),
    Column("scene_id", String),
    Column("strategy_label", String),
    Column("model", String),
    Column("input_tokens", Integer, default=0),
    Column("output_tokens", Integer, default=0),
    Column("cost_usd", Float, default=0.0),
    Column("recorded_at", String),
)

adapter_invocations = Table(
    "adapter_invocations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("show_id", String, nullable=False),
    Column("scene_id", String),
    Column("adapter_type", String, nullable=False),  # sub-agent | channel | tool
    Column("adapter_name", String),
    Column("method", String),
    Column("success", Integer, default=0),
    Column("duration_ms", Integer, default=0),
    Column("error_type", String),
    Column("invoked_at", String),
)

schema_validations = Table(
    "schema_validations",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("show_id", String, nullable=False),
    Column("scene_id", String),
    Column("output_name", String),
    Column("schema_spec", String),
    Column("passed", Integer, nullable=False),
    Column("details", Text),
    Column("validated_at", String),
)

delivery_artefacts = Table(
    "delivery_artefacts",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("show_id", String, nullable=False),
    Column("artefact_type", String, nullable=False),  # programme-md | programme-json | custom
    Column("path", String),
    Column("size_bytes", Integer),
    Column("delivered", Integer, default=0),
    Column("created_at", String),
)


def get_engine(db_path: str):
    """Return a SQLAlchemy engine for the given show DB path."""
    return create_engine(f"sqlite:///{db_path}", echo=False)


def apply_v1_schema(db_path: str) -> None:
    """Create all v1.0 new tables (idempotent — CREATE TABLE IF NOT EXISTS)."""
    engine = get_engine(db_path)
    # Only create the NEW tables, not the existing ones managed by state.py
    new_tables = [
        signed_tokens,
        retries,
        costs,
        adapter_invocations,
        schema_validations,
        delivery_artefacts,
    ]
    for table in new_tables:
        table.create(engine, checkfirst=True)
