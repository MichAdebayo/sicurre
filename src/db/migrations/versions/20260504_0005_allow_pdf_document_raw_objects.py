"""Allow pdf_document raw objects.

Revision ID: 20260504_0005
Revises: 3b182d057cb9
Create Date: 2026-05-04 14:30:00.000000
"""

from __future__ import annotations

from alembic import op

revision = "20260504_0005"
down_revision = "3b182d057cb9"
branch_labels = None
depends_on = None


CONSTRAINT_NAME = "ck_data_raw_object_object_type_allowed"
UPGRADE_OBJECT_TYPE_CHECK = (
    "object_type IN ('file', 'api_payload', 'html_page', 'pdf_document', "
    "'sql_export', 'bigdata_extract')"
)
DOWNGRADE_OBJECT_TYPE_CHECK = (
    "object_type IN ('file', 'api_payload', 'html_page', 'sql_export', "
    "'bigdata_extract')"
)


def _recreate_object_type_check(check_sql: str) -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"

    if is_sqlite:
        bind.exec_driver_sql("PRAGMA foreign_keys=OFF")
        bind.exec_driver_sql("DROP TABLE IF EXISTS _alembic_tmp_data_raw_object")
        try:
            with op.batch_alter_table("data_raw_object", recreate="always") as batch_op:
                batch_op.drop_constraint(CONSTRAINT_NAME, type_="check")
                batch_op.create_check_constraint(CONSTRAINT_NAME, check_sql)
        finally:
            bind.exec_driver_sql("PRAGMA foreign_keys=ON")
    else:
        # PostgreSQL supports direct ALTER TABLE constraint operations —
        # no table recreation needed (and it would fail due to FK dependencies).
        op.drop_constraint(CONSTRAINT_NAME, "data_raw_object", type_="check")
        op.create_check_constraint(CONSTRAINT_NAME, "data_raw_object", check_sql)


def upgrade() -> None:
    _recreate_object_type_check(UPGRADE_OBJECT_TYPE_CHECK)


def downgrade() -> None:
    _recreate_object_type_check(DOWNGRADE_OBJECT_TYPE_CHECK)
