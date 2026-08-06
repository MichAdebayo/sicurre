"""Add controlled operational exercise audit records.

Revision ID: 20260806_0007
Revises: 20260724_app_0006
"""

from __future__ import annotations

from alembic import op

from db.models.app_runtime import app_operational_exercise

revision = "20260806_0007"
down_revision = "20260724_app_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the operational exercise audit table."""
    app_operational_exercise.create(bind=op.get_bind(), checkfirst=True)


def downgrade() -> None:
    """Remove the operational exercise audit table."""
    app_operational_exercise.drop(bind=op.get_bind(), checkfirst=True)
