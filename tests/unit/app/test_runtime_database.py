from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from core.config import Settings
from db.runtime import _bind_qmark_parameters, _qualify_auth_tables, ensure_local_runtime_tables


def test_qmark_binding_creates_named_parameters() -> None:
    sql, bindings = _bind_qmark_parameters("SELECT ? AS one, ? AS two", [1, "two"])

    assert sql == "SELECT :p0 AS one, :p1 AS two"
    assert bindings == {"p0": 1, "p1": "two"}


def test_qmark_binding_rejects_parameter_mismatch() -> None:
    with pytest.raises(ValueError, match="placeholder count"):
        _bind_qmark_parameters("SELECT ?", [])


def test_auth_table_qualification_is_environment_specific(monkeypatch) -> None:
    monkeypatch.setattr(
        "db.runtime.get_settings",
        lambda: Settings(_env_file=None, environment="production", better_auth_schema="identity"),
    )
    assert _qualify_auth_tables('SELECT * FROM "user"') == 'SELECT * FROM identity."user"'

    monkeypatch.setattr(
        "db.runtime.get_settings", lambda: Settings(_env_file=None, environment="test")
    )
    assert _qualify_auth_tables('SELECT * FROM "user"') == 'SELECT * FROM "user"'


def test_local_runtime_table_creation_disposes_engine(monkeypatch) -> None:
    engine = SimpleNamespace(dispose=MagicMock())
    create_all = MagicMock()
    monkeypatch.setattr(
        "db.runtime.get_settings", lambda: Settings(_env_file=None, environment="test")
    )
    monkeypatch.setattr("db.runtime.create_engine", lambda _: engine)
    monkeypatch.setattr("db.runtime.Base.metadata.create_all", create_all)

    ensure_local_runtime_tables()

    create_all.assert_called_once_with(engine)
    engine.dispose.assert_called_once_with()


def test_production_does_not_create_runtime_tables(monkeypatch) -> None:
    create_engine = MagicMock()
    monkeypatch.setattr(
        "db.runtime.get_settings", lambda: Settings(_env_file=None, environment="production")
    )
    monkeypatch.setattr("db.runtime.create_engine", create_engine)

    ensure_local_runtime_tables()

    create_engine.assert_not_called()
