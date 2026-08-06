"""Application Alembic graph regression tests."""

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_application_migrations_form_one_resolvable_chain() -> None:
    """Reject missing predecessors and accidental multiple heads."""
    script = ScriptDirectory.from_config(Config("alembic.app.ini"))

    assert script.get_current_head() == "20260806_0007"
    assert script.get_revision("20260724_app_0006") is not None
