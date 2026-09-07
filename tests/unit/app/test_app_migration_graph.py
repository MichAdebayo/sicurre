"""Application Alembic graph regression tests."""

from unittest.mock import MagicMock

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_application_migrations_form_one_resolvable_chain() -> None:
    """Reject missing predecessors and accidental multiple heads."""
    script = ScriptDirectory.from_config(Config("alembic.app.ini"))

    # Assert the property, not the current head's name.
    heads = script.get_heads()
    assert len(heads) == 1, f"migration graph has branched: {heads}"

    # And the chain must walk from that head back to base without a gap.
    revisions = list(script.walk_revisions("base", heads[0]))
    assert revisions, "no revisions resolved from base to head"
    for revision in revisions:
        assert revision.module is not None

    assert script.get_revision("20260724_app_0006") is not None


def test_operational_exercise_migration_executes_both_directions(monkeypatch) -> None:
    """Exercise the release migration against Alembic's supplied bind."""
    script = ScriptDirectory.from_config(Config("alembic.app.ini"))
    migration = script.get_revision("20260806_0007").module
    bind = object()
    create = MagicMock()
    drop = MagicMock()
    monkeypatch.setattr(migration.op, "get_bind", lambda: bind)
    monkeypatch.setattr(migration.app_operational_exercise, "create", create)
    monkeypatch.setattr(migration.app_operational_exercise, "drop", drop)

    migration.upgrade()
    migration.downgrade()

    create.assert_called_once_with(bind=bind, checkfirst=True)
    drop.assert_called_once_with(bind=bind, checkfirst=True)


def test_domain_context_migration_executes_both_directions(monkeypatch) -> None:
    """Exercise domain attribution and preference reshaping in-process."""
    script = ScriptDirectory.from_config(Config("alembic.app.ini"))
    migration = script.get_revision("20260830_app_0008").module
    bind = object()

    class Inspector:
        quarantine_index_calls = 0
        quarantine_unique_calls = 0

        def get_columns(self, table: str) -> list[dict[str, str]]:
            if table == "app_alert_preference":
                return [{"name": "workspace_id"}]
            return []

        def get_indexes(self, table: str) -> list[dict[str, str]]:
            if table != "app_quarantine_item":
                return []
            self.quarantine_index_calls += 1
            if self.quarantine_index_calls == 3:
                return [{"name": "uq_app_quarantine_workspace_domain_message"}]
            return []

        def get_unique_constraints(self, table: str) -> list[dict[str, str]]:
            assert table == "app_quarantine_item"
            self.quarantine_unique_calls += 1
            if self.quarantine_unique_calls == 1:
                return [{"name": "uq_app_quarantine_workspace_message"}]
            return []

    inspector = Inspector()
    batches: list[MagicMock] = []

    def batch_alter_table(_table: str) -> MagicMock:
        batch = MagicMock()
        batch.__enter__.return_value = batch
        batches.append(batch)
        return batch

    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: inspector)
    monkeypatch.setattr(migration.op, "get_bind", lambda: bind)
    monkeypatch.setattr(migration.op, "batch_alter_table", batch_alter_table)
    monkeypatch.setattr(migration.app_alert_read, "create", MagicMock())
    monkeypatch.setattr(migration.app_alert_read, "drop", MagicMock())
    for operation in (
        "add_column",
        "create_index",
        "create_table",
        "drop_index",
        "drop_table",
        "execute",
        "rename_table",
    ):
        monkeypatch.setattr(migration.op, operation, MagicMock())

    migration.upgrade()
    migration.downgrade()

    migration.app_alert_read.create.assert_called_once_with(bind=bind, checkfirst=True)
    migration.app_alert_read.drop.assert_called_once_with(bind=bind, checkfirst=True)
    assert migration.op.add_column.call_count == 6
    assert migration.op.execute.call_count == 7
    assert migration.op.create_table.call_count == 2
    assert len(batches) == 6


def test_model_identity_migration_executes_both_directions(monkeypatch) -> None:
    """Exercise the model-identity migration in both directions."""
    script = ScriptDirectory.from_config(Config("alembic.app.ini"))
    migration = script.get_revision("20260904_app_0009").module

    existing: set[str] = set()

    class Inspector:
        def get_columns(self, table: str):
            assert table == "app_inference_event"
            return [{"name": name} for name in sorted(existing)]

    monkeypatch.setattr(migration.op, "get_bind", lambda: object())
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: Inspector())

    added: list[str] = []
    dropped: list[str] = []
    monkeypatch.setattr(
        migration.op, "add_column", lambda table, column: added.append(column.name)
    )
    monkeypatch.setattr(migration.op, "drop_column", lambda table, name: dropped.append(name))

    # Fresh table: both columns are added.
    migration.upgrade()
    assert added == ["model_version", "model_revision"]

    # Rerun against a table that already has them: nothing is added twice.
    existing.update(added)
    added.clear()
    migration.upgrade()
    assert added == [], "re-running the migration must be a no-op"

    # Downgrade removes exactly what it added.
    migration.downgrade()
    assert dropped == ["model_version", "model_revision"]

    # And a downgrade on a table without them does nothing.
    existing.clear()
    dropped.clear()
    migration.downgrade()
    assert dropped == [], "downgrade on a clean table must be a no-op"


def test_shield_status_key_migration_executes_both_directions(monkeypatch) -> None:
    """Widening and narrowing the Domain Shield key must both be runnable.

    The table was keyed on `domain` alone, so two workspaces protecting the same
    domain shared one row. Narrowing back cannot keep both, so the downgrade
    collapses to the most recently updated row rather than failing.
    """
    script = ScriptDirectory.from_config(Config("alembic.app.ini"))
    migration = script.get_revision("20260907_app_0010").module

    pk_columns: list[str] = ["domain"]

    class Inspector:
        def get_pk_constraint(self, table: str):
            assert table == "app_domain_shield_status"
            return {"constrained_columns": list(pk_columns)}

    monkeypatch.setattr(migration.op, "get_bind", lambda: object())
    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: Inspector())

    statements: list[str] = []
    created: list[list[str]] = []
    dropped: list[str] = []
    monkeypatch.setattr(migration.op, "execute", lambda stmt: statements.append(str(stmt)))
    monkeypatch.setattr(
        migration.op, "drop_constraint",
        lambda name, table, type_: dropped.append(name),
    )
    monkeypatch.setattr(
        migration.op, "create_primary_key",
        lambda name, table, cols: created.append(list(cols)),
    )

    migration.upgrade()
    assert created == [["workspace_id", "domain"]]
    assert dropped == ["pk_app_domain_shield_status"]
    assert any("workspace_id IS NULL" in s for s in statements), (
        "an ownerless row cannot be keyed and must be removed first"
    )

    # Re-running against the widened key must be a no-op, not a second attempt.
    pk_columns = ["workspace_id", "domain"]
    created.clear(); dropped.clear(); statements.clear()
    migration.upgrade()
    assert created == [] and dropped == [], "upgrade is not idempotent"

    migration.downgrade()
    assert created == [["domain"]]
    assert any("updated_at" in s for s in statements), (
        "the downgrade must keep the most recently updated row per domain"
    )
