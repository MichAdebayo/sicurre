"""Add model provenance and immutable evaluation-set records.

Revision ID: 20260719_0002
Revises: 20260708_0001
Create Date: 2026-07-19 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from db.models.mlops import (
    DataEvaluationSet,
    MlModelDeployment,
    MlModelEvaluation,
    MlModelVersion,
)

revision = "20260719_0002"
down_revision = "20260708_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add training artifact columns and model-governance tables."""
    bind = op.get_bind()
    dataset_columns = {column["name"] for column in sa.inspect(bind).get_columns("data_dataset")}
    columns = {
        "artifact_uri": sa.Column("artifact_uri", sa.Text(), nullable=True),
        "content_checksum": sa.Column("content_checksum", sa.Text(), nullable=True),
        "schema_version": sa.Column("schema_version", sa.Text(), nullable=True),
    }
    for name, column in columns.items():
        if name not in dataset_columns:
            op.add_column("data_dataset", column)
    for table in (
        DataEvaluationSet.__table__,
        MlModelVersion.__table__,
        MlModelEvaluation.__table__,
        MlModelDeployment.__table__,
    ):
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    """Remove model-governance tables and artifact metadata columns."""
    bind = op.get_bind()
    for table in (
        MlModelDeployment.__table__,
        MlModelEvaluation.__table__,
        MlModelVersion.__table__,
        DataEvaluationSet.__table__,
    ):
        table.drop(bind=bind, checkfirst=True)
    op.drop_column("data_dataset", "schema_version")
    op.drop_column("data_dataset", "content_checksum")
    op.drop_column("data_dataset", "artifact_uri")
