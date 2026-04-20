"""add v1.0 tables: signed_tokens, retries, costs, adapter_invocations, schema_validations, delivery_artefacts

Revision ID: 0001
Revises:
Create Date: 2026-04-20

These tables are additive — they do not modify the existing tables managed by state.py.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "signed_tokens",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("show_id", sa.String, nullable=False),
        sa.Column("token", sa.String, nullable=False, unique=True),
        sa.Column("purpose", sa.String, nullable=False),
        sa.Column("matter_id", sa.Integer),
        sa.Column("used", sa.Integer, default=0),
        sa.Column("created_at", sa.String),
        sa.Column("expires_at", sa.String),
    )

    op.create_table(
        "retries",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("show_id", sa.String, nullable=False),
        sa.Column("scene_id", sa.String, nullable=False),
        sa.Column("strategy_label", sa.String),
        sa.Column("attempt_number", sa.Integer, nullable=False),
        sa.Column("error_type", sa.String),
        sa.Column("error_message", sa.Text),
        sa.Column("retried_at", sa.String),
    )

    op.create_table(
        "costs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("show_id", sa.String, nullable=False),
        sa.Column("scene_id", sa.String),
        sa.Column("strategy_label", sa.String),
        sa.Column("model", sa.String),
        sa.Column("input_tokens", sa.Integer, default=0),
        sa.Column("output_tokens", sa.Integer, default=0),
        sa.Column("cost_usd", sa.Float, default=0.0),
        sa.Column("recorded_at", sa.String),
    )

    op.create_table(
        "adapter_invocations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("show_id", sa.String, nullable=False),
        sa.Column("scene_id", sa.String),
        sa.Column("adapter_type", sa.String, nullable=False),
        sa.Column("adapter_name", sa.String),
        sa.Column("method", sa.String),
        sa.Column("success", sa.Integer, default=0),
        sa.Column("duration_ms", sa.Integer, default=0),
        sa.Column("error_type", sa.String),
        sa.Column("invoked_at", sa.String),
    )

    op.create_table(
        "schema_validations",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("show_id", sa.String, nullable=False),
        sa.Column("scene_id", sa.String),
        sa.Column("output_name", sa.String),
        sa.Column("schema_spec", sa.String),
        sa.Column("passed", sa.Integer, nullable=False),
        sa.Column("details", sa.Text),
        sa.Column("validated_at", sa.String),
    )

    op.create_table(
        "delivery_artefacts",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("show_id", sa.String, nullable=False),
        sa.Column("artefact_type", sa.String, nullable=False),
        sa.Column("path", sa.String),
        sa.Column("size_bytes", sa.Integer),
        sa.Column("delivered", sa.Integer, default=0),
        sa.Column("created_at", sa.String),
    )


def downgrade() -> None:
    op.drop_table("delivery_artefacts")
    op.drop_table("schema_validations")
    op.drop_table("adapter_invocations")
    op.drop_table("costs")
    op.drop_table("retries")
    op.drop_table("signed_tokens")
