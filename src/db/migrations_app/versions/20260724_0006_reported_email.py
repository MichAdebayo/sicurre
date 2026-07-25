"""Add workspace-scoped reported-email evidence.

Revision ID: 20260724_app_0006
Revises: 20260715_app_0005
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260724_app_0006"
down_revision = "20260715_app_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the private reported-email evidence index."""
    if "app_reported_email" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "app_reported_email",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("workspace_member_user_id", sa.Text(), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'received'")),
        sa.Column("received_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "content_hash",
            name="uq_app_reported_email_workspace_hash",
        ),
    )
    op.create_index(
        "ix_app_reported_email_workspace_id",
        "app_reported_email",
        ["workspace_id"],
    )


def downgrade() -> None:
    """Remove reported-email evidence storage."""
    op.drop_index("ix_app_reported_email_workspace_id", table_name="app_reported_email")
    op.drop_table("app_reported_email")
