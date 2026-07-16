"""Add tenant-scoped support requests.

Revision ID: 20260715_app_0003
Revises: 20260715_app_0002
Create Date: 2026-07-15 02:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260715_app_0003"
down_revision = "20260715_app_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create durable support-ticket storage when it is not in the baseline."""
    if "app_support_request" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "app_support_request",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("workspace_member_user_id", sa.Text(), nullable=False),
        sa.Column("requester_name", sa.Text(), nullable=False),
        sa.Column("requester_email", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'open'")),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_app_support_request_workspace_id",
        "app_support_request",
        ["workspace_id"],
    )
    op.create_index(
        "ix_app_support_request_status",
        "app_support_request",
        ["status"],
    )


def downgrade() -> None:
    """Remove support-ticket storage."""
    op.drop_index("ix_app_support_request_status", table_name="app_support_request")
    op.drop_index("ix_app_support_request_workspace_id", table_name="app_support_request")
    op.drop_table("app_support_request")
