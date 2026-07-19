"""Create current data-platform baseline.

Revision ID: 20260708_0001
Revises:
Create Date: 2026-07-08 00:00:00.000000

This repository is still pre-production for the data-platform database.
The earlier exploratory migration chain has been retired so a fresh local or
Neon database can be created with the current ORM schema in one pass.
"""

from __future__ import annotations

from alembic import op

from core.database import Base
from db.models import lineage, mlops  # noqa: F401

revision = "20260708_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
