"""The shield-status rekey must run on a real engine, not just a stubbed one.

The first version of this migration was verified two ways - its logic against
stub operations, and its effect against the production PostgreSQL schema - and
was still broken. SQLite cannot ALTER a constraint at all, and the downgrade
used `DELETE ... USING`, which is PostgreSQL-only syntax. Both failed at
container start, where the app runs its migrations before serving.

These tests drive the real migration functions against a real SQLite database,
which is what local development and the Docker smoke stack both use.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

migration = ScriptDirectory.from_config(Config("alembic.app.ini")).get_revision(
    "20260907_app_0010"
).module

_TABLE = "app_domain_shield_status"

# The table as it stood before this migration: keyed on the domain alone.
_LEGACY_DDL = f"""
CREATE TABLE {_TABLE} (
  domain TEXT NOT NULL, workspace_id TEXT NOT NULL,
  spf_valid INTEGER NOT NULL, spf_record TEXT,
  dkim_valid INTEGER NOT NULL, dkim_record TEXT,
  dmarc_valid INTEGER NOT NULL, dmarc_record TEXT, dmarc_policy TEXT,
  ssl_valid INTEGER NOT NULL, ssl_days_remaining INTEGER NOT NULL,
  reputation_score INTEGER NOT NULL, score_grade TEXT NOT NULL, updated_at TEXT NOT NULL,
  CONSTRAINT pk_app_domain_shield_status PRIMARY KEY (domain)
)
"""


def _row(domain: str, workspace: str, updated_at: str, days: int = 77) -> str:
    return (
        f"INSERT INTO {_TABLE} VALUES ('{domain}','{workspace}',1,'v=spf1 -all',"
        f"1,NULL,1,NULL,'reject',1,{days},100,'A','{updated_at}')"
    )


@pytest.fixture
def legacy_db(tmp_path: Path) -> Iterator[sa.Engine]:
    """A SQLite database carrying the pre-migration schema and one row."""
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'app.db'}")
    with engine.begin() as conn:
        conn.execute(sa.text(_LEGACY_DDL))
        conn.execute(
            sa.text(f"CREATE INDEX ix_{_TABLE}_workspace_id ON {_TABLE} (workspace_id)")
        )
        conn.execute(sa.text(_row("vinse.app", "ws-a", "2026-09-01")))
    yield engine
    engine.dispose()


def _run(engine: sa.Engine, direction: str) -> None:
    """Drive the migration through the real `op`, not a stub.

    Binding alembic's `op` proxy to a live MigrationContext is the whole point:
    stubbed operations accept DDL that the SQLite dialect refuses outright.
    """
    with engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            getattr(migration, direction)()


def _pk(engine: sa.Engine) -> list[str]:
    return list(sa.inspect(engine).get_pk_constraint(_TABLE)["constrained_columns"])


def _indexes(engine: sa.Engine) -> list[str]:
    return sorted(index["name"] or "" for index in sa.inspect(engine).get_indexes(_TABLE))


def test_the_rekey_runs_on_sqlite(legacy_db: sa.Engine) -> None:
    """SQLite cannot ALTER a constraint; the table has to be rebuilt."""
    assert _pk(legacy_db) == ["domain"]
    _run(legacy_db, "upgrade")
    assert _pk(legacy_db) == ["workspace_id", "domain"]


def test_the_rebuild_keeps_the_rows(legacy_db: sa.Engine) -> None:
    """A copy-and-move that loses data is worse than the bug it fixes."""
    _run(legacy_db, "upgrade")
    with legacy_db.connect() as conn:
        rows = conn.execute(
            sa.text(f"SELECT domain, workspace_id, ssl_days_remaining FROM {_TABLE}")
        ).all()
    assert rows == [("vinse.app", "ws-a", 77)]


def test_the_rebuild_keeps_the_indexes(legacy_db: sa.Engine) -> None:
    """A rebuilt table does not inherit the indexes of the one it replaced."""
    before = _indexes(legacy_db)
    assert f"ix_{_TABLE}_workspace_id" in before
    _run(legacy_db, "upgrade")
    assert _indexes(legacy_db) == before


def test_two_workspaces_can_hold_the_same_domain(legacy_db: sa.Engine) -> None:
    """The point of the whole migration, checked on the rebuilt table."""
    _run(legacy_db, "upgrade")
    with legacy_db.begin() as conn:
        conn.execute(sa.text(_row("vinse.app", "ws-b", "2026-09-02", days=50)))
        count = conn.execute(
            sa.text(f"SELECT count(*) FROM {_TABLE} WHERE domain = 'vinse.app'")
        ).scalar()
    assert count == 2


def test_the_upgrade_is_idempotent(legacy_db: sa.Engine) -> None:
    """Re-running against the widened key must be a no-op, not a second rebuild."""
    _run(legacy_db, "upgrade")
    _run(legacy_db, "upgrade")
    assert _pk(legacy_db) == ["workspace_id", "domain"]
    assert _indexes(legacy_db) == [f"ix_{_TABLE}_workspace_id"]


def test_the_downgrade_runs_on_sqlite_and_keeps_the_newest(legacy_db: sa.Engine) -> None:
    """`DELETE ... USING` is PostgreSQL-only and failed here."""
    _run(legacy_db, "upgrade")
    with legacy_db.begin() as conn:
        conn.execute(sa.text(_row("vinse.app", "ws-b", "2026-09-05", days=50)))

    _run(legacy_db, "downgrade")

    assert _pk(legacy_db) == ["domain"]
    with legacy_db.connect() as conn:
        rows = conn.execute(sa.text(f"SELECT domain, workspace_id FROM {_TABLE}")).all()
    assert rows == [("vinse.app", "ws-b")], "the most recently updated row must survive"


def test_the_downgrade_is_idempotent(legacy_db: sa.Engine) -> None:
    """Already narrow is nothing to do."""
    _run(legacy_db, "downgrade")
    assert _pk(legacy_db) == ["domain"]


def test_the_key_columns_cannot_be_null(legacy_db: sa.Engine) -> None:
    """Why the migration carries no guard for an unowned row.

    An earlier draft deleted rows with a null workspace_id before rekeying.
    That can never match: the column is NOT NULL in every deployment, and once
    it joins the primary key the constraint is structural rather than
    incidental - a key column cannot be null.
    """
    _run(legacy_db, "upgrade")
    with pytest.raises(sa.exc.IntegrityError):
        with legacy_db.begin() as conn:
            conn.execute(sa.text(f"UPDATE {_TABLE} SET workspace_id = NULL"))

    columns = {c["name"]: c for c in sa.inspect(legacy_db).get_columns(_TABLE)}
    assert columns["workspace_id"]["nullable"] is False
    assert columns["domain"]["nullable"] is False
