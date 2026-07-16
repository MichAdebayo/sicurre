"""Store the timezone used to evaluate notification quiet hours.

Revision ID: 20260715_app_0005
Revises: 20260715_app_0004
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260715_app_0005"
down_revision = "20260715_app_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the user-local timezone unless the current baseline already has it."""
    columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("app_alert_preference")
    }
    if "timezone" not in columns:
        op.add_column(
            "app_alert_preference",
            sa.Column(
                "timezone",
                sa.Text(),
                nullable=False,
                server_default="Europe/Paris",
            ),
        )


def downgrade() -> None:
    """Remove the quiet-hours timezone."""
    columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("app_alert_preference")
    }
    if "timezone" in columns:
        with op.batch_alter_table("app_alert_preference") as batch_op:
            batch_op.drop_column("timezone")
