"""Key the Domain Shield status on the workspace as well as the domain.

Revision ID: 20260907_app_0010
Revises: 20260904_app_0009

Two workspaces protecting the same domain previously shared one status row.
The model declares the composite ``(workspace_id, domain)`` key, so a database
created from scratch is already correct and this migration is a no-op there;
it rebuilds the key only on databases that predate the change.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260907_app_0010"
down_revision = "20260904_app_0009"
branch_labels = None
depends_on = None

_TABLE = "app_domain_shield_status"
_PK = "pk_app_domain_shield_status"


def _primary_key_columns(bind: sa.engine.Connection) -> list[str]:
    constraint = sa.inspect(bind).get_pk_constraint(_TABLE)
    return list(constraint.get("constrained_columns") or [])


def _rekey(bind: sa.engine.Connection, pk_columns: list[str]) -> None:
    """Move the primary key to `pk_columns`, whatever the dialect allows.

    SQLite cannot ALTER a constraint at all, so the table is rebuilt by
    copy-and-move. The rebuild is driven by the live table's own reflected
    definition rather than a copy of the schema written out here, which would
    silently drift; its indexes are carried across explicitly, because a
    rebuilt table does not inherit the indexes of the one it replaces.
    """
    if bind.dialect.name == "sqlite":
        live = sa.Table(_TABLE, sa.MetaData(), autoload_with=bind)
        target = sa.Table(
            _TABLE,
            sa.MetaData(),
            *[sa.Column(c.name, c.type, nullable=c.nullable) for c in live.columns],
            sa.PrimaryKeyConstraint(*pk_columns, name=_PK),
        )
        for index in live.indexes:
            sa.Index(
                index.name,
                *[target.c[column.name] for column in index.columns],
                unique=index.unique,
            )
        with op.batch_alter_table(_TABLE, copy_from=target, recreate="always"):
            pass
        return

    op.drop_constraint(_PK, _TABLE, type_="primary")
    op.create_primary_key(_PK, _TABLE, pk_columns)


def upgrade() -> None:
    """Widen the primary key to (workspace_id, domain)."""
    bind = op.get_bind()
    if sorted(_primary_key_columns(bind)) == ["domain", "workspace_id"]:
        return

    # No guard is needed for an unowned row: workspace_id is NOT NULL in every
    # deployment, and joining the primary key makes that structural rather than
    # incidental. A key column cannot be null.
    _rekey(bind, ["workspace_id", "domain"])


def downgrade() -> None:
    """Return to a domain-only key, keeping one row per domain.

    Narrowing the key cannot preserve two workspaces' rows for one domain, so
    the most recently updated row wins and the rest are dropped. The delete is
    written as a correlated EXISTS rather than `DELETE ... USING`, which is
    PostgreSQL-only syntax.
    """
    bind = op.get_bind()
    if _primary_key_columns(bind) == ["domain"]:
        return

    op.execute(
        sa.text(
            f"""
            DELETE FROM {_TABLE}
            WHERE EXISTS (
                SELECT 1 FROM {_TABLE} AS newer
                WHERE newer.domain = {_TABLE}.domain
                  AND (
                        newer.updated_at > {_TABLE}.updated_at
                     OR (newer.updated_at = {_TABLE}.updated_at
                         AND newer.workspace_id > {_TABLE}.workspace_id)
                  )
            )
            """
        )
    )
    _rekey(bind, ["domain"])
