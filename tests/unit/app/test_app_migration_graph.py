"""Application Alembic graph regression tests."""

from unittest.mock import MagicMock

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_application_migrations_form_one_resolvable_chain() -> None:
    """Reject missing predecessors and accidental multiple heads."""
    script = ScriptDirectory.from_config(Config("alembic.app.ini"))

    assert script.get_current_head() == "20260830_app_0008"
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
