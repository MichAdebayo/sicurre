"""Key the Domain Shield status on the workspace as well as the domain.

Revision ID: 20260907_app_0010
Revises: 20260904_app_0009

The table was keyed on `domain` alone, so two workspaces protecting the same
domain shared one row and overwrote each other's status. That is not
hypothetical here: vinse.app carried two active integrations in two workspaces
at once. Reads were already scoped by workspace, so the row a customer saw
could be a status written for someone else's copy of the domain.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260907_app_0010"
down_revision = "20260904_app_0009"
branch_labels = None
depends_on = None

_TABLE = "app_domain_shield_status"
_OLD_PK = "pk_app_domain_shield_status"


def _primary_key_columns(bind: sa.engine.Connection) -> list[str]:
    inspector = sa.inspect(bind)
    constraint = inspector.get_pk_constraint(_TABLE)
    return list(constraint.get("constrained_columns") or [])


def upgrade() -> None:
    """Widen the primary key to (workspace_id, domain)."""
    bind = op.get_bind()
    if sorted(_primary_key_columns(bind)) == ["domain", "workspace_id"]:
        return

    # A row whose workspace is unknown cannot belong to anyone; keying it would
    # only preserve a collision under a new name.
    op.execute(sa.text(f"DELETE FROM {_TABLE} WHERE workspace_id IS NULL"))
    op.drop_constraint(_OLD_PK, _TABLE, type_="primary")
    op.create_primary_key(_OLD_PK, _TABLE, ["workspace_id", "domain"])


def downgrade() -> None:
    """Return to a domain-only key, keeping one row per domain.

    Narrowing the key cannot preserve two workspaces' rows for one domain, so
    the most recently updated row wins and the rest are dropped.
    """
    bind = op.get_bind()
    if _primary_key_columns(bind) == ["domain"]:
        return

    op.execute(
        sa.text(
            f"""
            DELETE FROM {_TABLE} a
            USING {_TABLE} b
            WHERE a.domain = b.domain
              AND a.workspace_id <> b.workspace_id
              AND (a.updated_at, a.workspace_id) < (b.updated_at, b.workspace_id)
            """
        )
    )
    op.drop_constraint(_OLD_PK, _TABLE, type_="primary")
    op.create_primary_key(_OLD_PK, _TABLE, ["domain"])
