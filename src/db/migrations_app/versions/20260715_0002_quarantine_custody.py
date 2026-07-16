"""Add durable quarantine custody and release metadata.

Revision ID: 20260715_app_0002
Revises: 20260711_app_0001
Create Date: 2026-07-15 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260715_app_0002"
down_revision = "20260711_app_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add MIME custody, delivery state, and inbound idempotency fields."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("app_quarantine_item")}
    desired_columns = {
        "raw_storage_uri": sa.Text(),
        "raw_content_hash": sa.Text(),
        "raw_size_bytes": sa.Integer(),
        "delivery_message_id": sa.Text(),
        "delivered_at": sa.Text(),
        "last_delivery_error": sa.Text(),
    }
    for name, column_type in desired_columns.items():
        if name not in existing_columns:
            with op.batch_alter_table("app_quarantine_item") as batch:
                batch.add_column(sa.Column(name, column_type, nullable=True))

    unique_names = {
        constraint["name"] for constraint in inspector.get_unique_constraints("app_quarantine_item")
    }
    index_names = {index["name"] for index in inspector.get_indexes("app_quarantine_item")}
    if "uq_app_quarantine_workspace_message" not in unique_names | index_names:
        with op.batch_alter_table("app_quarantine_item") as batch:
            batch.create_unique_constraint(
                "uq_app_quarantine_workspace_message",
                ["workspace_id", "message_id"],
            )


def downgrade() -> None:
    """Remove MIME custody and delivery metadata."""
    with op.batch_alter_table("app_quarantine_item") as batch:
        batch.drop_constraint("uq_app_quarantine_workspace_message", type_="unique")
        for column_name in (
            "last_delivery_error",
            "delivered_at",
            "delivery_message_id",
            "raw_size_bytes",
            "raw_content_hash",
            "raw_storage_uri",
        ):
            batch.drop_column(column_name)
