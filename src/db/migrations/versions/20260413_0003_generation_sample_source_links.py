"""Add generation sample source link table.

Revision ID: 20260413_0003
Revises: 20260408_0002
Create Date: 2026-04-13 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260413_0003"
down_revision = "20260408_0002"
branch_labels = None
depends_on = None


LINK_ROLE_CHECK = (
    "link_role IN ('generation_seed', 'sample_input', 'nearest_reference')"
)


def upgrade() -> None:
    op.create_table(
        "data_generation_sample_source_link",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("generation_sample_id", sa.Uuid(), nullable=False),
        sa.Column("raw_record_id", sa.Uuid(), nullable=False),
        sa.Column("link_role", sa.Text(), nullable=False),
        sa.Column("link_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            LINK_ROLE_CHECK,
            name="ck_data_generation_sample_source_link_link_role_allowed",
        ),
        sa.ForeignKeyConstraint(
            ["generation_sample_id"],
            ["data_generation_sample.id"],
            name=(
                "fk_data_generation_sample_source_link_generation_sample_id_"
                "data_generation_sample"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["raw_record_id"],
            ["data_raw_record.id"],
            name=(
                "fk_data_generation_sample_source_link_raw_record_id_"
                "data_raw_record"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_data_generation_sample_source_link"),
        sa.UniqueConstraint(
            "generation_sample_id",
            "raw_record_id",
            "link_role",
            name="uq_generation_sample_source_link_sample_record_role",
        ),
    )
    op.create_index(
        "idx_generation_sample_source_link_sample_order",
        "data_generation_sample_source_link",
        ["generation_sample_id", "link_order"],
        unique=False,
    )
    op.create_index(
        "idx_generation_sample_source_link_raw_record",
        "data_generation_sample_source_link",
        ["raw_record_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_generation_sample_source_link_raw_record",
        table_name="data_generation_sample_source_link",
    )
    op.drop_index(
        "idx_generation_sample_source_link_sample_order",
        table_name="data_generation_sample_source_link",
    )
    op.drop_table("data_generation_sample_source_link")