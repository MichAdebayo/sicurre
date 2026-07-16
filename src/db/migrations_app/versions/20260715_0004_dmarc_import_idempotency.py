"""Make DMARC aggregate report imports idempotent.

Revision ID: 20260715_app_0004
Revises: 20260715_app_0003
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260715_app_0004"
down_revision = "20260715_app_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add a unique deterministic fingerprint for each imported report record."""
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("app_dmarc_report_summary")}
    if "report_fingerprint" in columns:
        return
    op.add_column(
        "app_dmarc_report_summary",
        sa.Column("report_fingerprint", sa.Text(), nullable=True),
    )
    op.create_index(
        "ux_app_dmarc_report_workspace_fingerprint",
        "app_dmarc_report_summary",
        ["workspace_id", "report_fingerprint"],
        unique=True,
    )


def downgrade() -> None:
    """Remove DMARC import fingerprints."""
    inspector = sa.inspect(op.get_bind())
    indexes = {index["name"] for index in inspector.get_indexes("app_dmarc_report_summary")}
    if "ux_app_dmarc_report_workspace_fingerprint" in indexes:
        op.drop_index(
            "ux_app_dmarc_report_workspace_fingerprint",
            table_name="app_dmarc_report_summary",
        )
    columns = {column["name"] for column in inspector.get_columns("app_dmarc_report_summary")}
    if "report_fingerprint" in columns:
        with op.batch_alter_table("app_dmarc_report_summary") as batch_op:
            batch_op.drop_column("report_fingerprint")
