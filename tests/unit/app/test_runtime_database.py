from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.config import Settings
from core.database import get_async_session
from db.runtime import (
    _bind_qmark_parameters,
    _initialized_runtime_urls,
    _qualify_auth_tables,
    ensure_local_runtime_tables,
    execute_runtime_query,
)

TEST_SECRET_KEY = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


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
        lambda: Settings(
            _env_file=None,
            environment="production",
            better_auth_schema="identity",
            secret_encryption_key=TEST_SECRET_KEY,
        ),
    )
    assert _qualify_auth_tables('SELECT * FROM "user"') == 'SELECT * FROM identity."user"'

    monkeypatch.setattr(
        "db.runtime.get_settings", lambda: Settings(_env_file=None, environment="test")
    )
    assert _qualify_auth_tables('SELECT * FROM "user"') == 'SELECT * FROM "user"'


def test_local_runtime_table_creation_disposes_engine(monkeypatch) -> None:
    _initialized_runtime_urls.clear()
    engine = SimpleNamespace(dispose=MagicMock())
    create_all = MagicMock()
    monkeypatch.setattr(
        "db.runtime.get_settings", lambda: Settings(_env_file=None, environment="test")
    )
    monkeypatch.setattr("db.runtime.create_engine", lambda _: engine)
    monkeypatch.setattr("db.runtime.Base.metadata.create_all", create_all)

    ensure_local_runtime_tables()
    ensure_local_runtime_tables()

    create_all.assert_called_once_with(engine)
    engine.dispose.assert_called_once_with()


def test_production_does_not_create_runtime_tables(monkeypatch) -> None:
    create_engine = MagicMock()
    monkeypatch.setattr(
        "db.runtime.get_settings",
        lambda: Settings(
            _env_file=None,
            environment="production",
            secret_encryption_key=TEST_SECRET_KEY,
        ),
    )
    monkeypatch.setattr("db.runtime.create_engine", create_engine)

    ensure_local_runtime_tables()

    create_engine.assert_not_called()


@pytest.mark.asyncio
async def test_async_session_dependency_yields_and_closes(monkeypatch) -> None:
    session = object()

    class SessionContext:
        async def __aenter__(self) -> object:
            return session

        async def __aexit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr("core.database.AsyncSessionFactory", SessionContext)

    dependency = get_async_session()
    assert await anext(dependency) is session
    with pytest.raises(StopAsyncIteration):
        await anext(dependency)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("returns_rows", "mapped_rows", "expected"),
    [
        (True, [{"value": 7}], [{"value": 7}]),
        (False, [], []),
    ],
)
async def test_execute_runtime_query_maps_rows_and_writes(
    monkeypatch, returns_rows: bool, mapped_rows: list[dict[str, int]], expected: list[dict[str, int]]
) -> None:
    result = SimpleNamespace(
        returns_rows=returns_rows,
        mappings=lambda: SimpleNamespace(all=lambda: mapped_rows),
    )
    connection = SimpleNamespace(execute=AsyncMock(return_value=result))

    class Transaction:
        async def __aenter__(self) -> object:
            return connection

        async def __aexit__(self, *_args: object) -> None:
            return None

    engine = SimpleNamespace(begin=Transaction)
    monkeypatch.setattr("db.runtime.get_app_engine", lambda: engine)
    monkeypatch.setattr("db.runtime._qualify_auth_tables", lambda sql: sql)

    assert await execute_runtime_query("SELECT ?", [7]) == expected
    connection.execute.assert_awaited_once()
