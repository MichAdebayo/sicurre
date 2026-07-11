"""Create the Sicurre application runtime baseline.

Revision ID: 20260711_app_0001
Revises:
Create Date: 2026-07-11 00:00:00.000000
"""

from __future__ import annotations

from alembic import op

from core.database import Base
from db.models import app_runtime

revision = "20260711_app_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create every application-owned table."""
    bind = op.get_bind()
    for table_name in app_runtime.APP_TABLE_NAMES:
        Base.metadata.tables[table_name].create(bind=bind, checkfirst=True)


def downgrade() -> None:
    """Drop every application-owned table."""
    bind = op.get_bind()
    for table_name in reversed(app_runtime.APP_TABLE_NAMES):
        Base.metadata.tables[table_name].drop(bind=bind, checkfirst=True)
