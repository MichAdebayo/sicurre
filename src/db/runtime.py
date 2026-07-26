"""Small cross-dialect query boundary for Sicurre application routes."""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache
from threading import Lock
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from core.config import get_settings
from core.database import Base
from db.models import app_runtime  # noqa: F401

_runtime_table_lock = Lock()
_initialized_runtime_urls: set[str] = set()


def _bind_qmark_parameters(sql: str, params: Sequence[Any]) -> tuple[str, dict[str, Any]]:
    """Convert DB-API qmark placeholders to SQLAlchemy named parameters."""
    pieces = sql.split("?")
    if len(pieces) - 1 != len(params):
        raise ValueError("SQL placeholder count does not match parameter count")
    rendered = pieces[0]
    bindings: dict[str, Any] = {}
    for index, value in enumerate(params):
        name = f"p{index}"
        bindings[name] = value
        rendered += f":{name}{pieces[index + 1]}"
    return rendered, bindings


def _qualify_auth_tables(sql: str) -> str:
    settings = get_settings()
    if settings.environment.strip().lower() != "production":
        return sql
    schema = settings.better_auth_schema
    return sql.replace('"user"', f'{schema}."user"')


@lru_cache(maxsize=1)
def get_app_engine() -> AsyncEngine:
    """Return the application database engine for SQLite or PostgreSQL."""
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


def ensure_local_runtime_tables() -> None:
    """Create runtime tables for local SQLite; production relies on Alembic."""
    settings = get_settings()
    if settings.environment.strip().lower() == "production":
        return
    database_url = settings.sync_database_url
    with _runtime_table_lock:
        if database_url in _initialized_runtime_urls:
            return
        engine = create_engine(database_url)
        try:
            Base.metadata.create_all(engine)
        finally:
            engine.dispose()
        _initialized_runtime_urls.add(database_url)


async def execute_runtime_query(
    sql: str,
    params: Sequence[Any] = (),
) -> list[dict[str, Any]]:
    """Execute one committed app query and return mapping rows when present."""
    qualified_sql = _qualify_auth_tables(sql)
    statement_sql, bindings = _bind_qmark_parameters(qualified_sql, params)
    async with get_app_engine().begin() as connection:
        result = await connection.execute(text(statement_sql), bindings)
        if not result.returns_rows:
            return []
        return [dict(row) for row in result.mappings().all()]
