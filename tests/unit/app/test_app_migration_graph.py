"""Application Alembic graph regression tests."""

from unittest.mock import MagicMock

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_application_migrations_form_one_resolvable_chain() -> None:
    """Reject missing predecessors and accidental multiple heads."""
    script = ScriptDirectory.from_config(Config("alembic.app.ini"))

    assert script.get_current_head() == "20260806_0007"
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
