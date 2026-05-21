"""Add kaggle_version_id and published_at to data_dataset.

Revision ID: 20260521_0006
Revises: 20260504_0005
Create Date: 2026-05-21 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260521_0006"
down_revision = "20260504_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("data_dataset") as batch_op:
        batch_op.add_column(sa.Column("kaggle_version_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("data_dataset") as batch_op:
        batch_op.drop_column("published_at")
        batch_op.drop_column("kaggle_version_id")
