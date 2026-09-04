"""Record which model produced each inference verdict.

Revision ID: 20260904_app_0009
Revises: 20260830_app_0008

The inference service returns its identity on every classification -
X-Sicurre-Model-Version and X-Sicurre-Model-Revision - and the application
discarded both. A verdict in the threat journal could therefore not be
attributed to the model that produced it, which is the question an audit of a
disputed classification starts with, and the one a retrained model makes
unanswerable retrospectively.

Both columns are nullable: rows written before this migration genuinely do not
know their model, and inventing a value for them would be worse than a null
that says so.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260904_app_0009"
down_revision = "20260830_app_0008"
branch_labels = None
depends_on = None

_COLUMNS = (
    sa.Column("model_version", sa.Text(), nullable=True),
    sa.Column("model_revision", sa.Text(), nullable=True),
)


def _add_column(table: str, column: sa.Column) -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}
    if column.name not in columns:
        op.add_column(table, column)


def _drop_column(table: str, name: str) -> None:
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}
    if name in columns:
        op.drop_column(table, name)


def upgrade() -> None:
    for column in _COLUMNS:
        _add_column("app_inference_event", column)


def downgrade() -> None:
    for column in _COLUMNS:
        _drop_column("app_inference_event", column.name)
