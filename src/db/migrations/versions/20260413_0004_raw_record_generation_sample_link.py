"""Link promoted raw records back to generation samples.

Revision ID: 20260413_0004
Revises: 20260413_0003
Create Date: 2026-04-13 00:00:01.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260413_0004"
down_revision = "20260413_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("data_raw_record") as batch_op:
        batch_op.add_column(sa.Column("generation_sample_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_data_raw_record_generation_sample_id_data_generation_sample",
            "data_generation_sample",
            ["generation_sample_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_index(
            "idx_data_raw_record_generation_sample_id",
            ["generation_sample_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("data_raw_record") as batch_op:
        batch_op.drop_index("idx_data_raw_record_generation_sample_id")
        batch_op.drop_constraint(
            "fk_data_raw_record_generation_sample_id_data_generation_sample",
            type_="foreignkey",
        )
        batch_op.drop_column("generation_sample_id")