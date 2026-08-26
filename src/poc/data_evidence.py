"""Read-only access to local data-platform evidence for the POC."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool


class PocDataEvidenceStore:
    """Query the validated local POC data-platform database lazily."""

    def __init__(self, database_path: Path, retries: int = 4, retry_delay: float = 0.2) -> None:
        """Configure local persistence without opening a database connection."""
        self._database_path = database_path
        self._retries = retries
        self._retry_delay = retry_delay
        self._engine: Engine | None = None

    @property
    def engine(self) -> Engine:
        """Create the SQLite engine only when evidence is requested."""
        if self._engine is None:
            self._engine = create_engine(
                f"sqlite:///{self._database_path}",
                future=True,
                poolclass=NullPool,
            )
        return self._engine

    def table_exists(self, table_name: str) -> bool:
        """Return whether a local evidence table exists."""
        try:
            return bool(inspect(self.engine).has_table(table_name))
        except OperationalError:
            return False

    def query(self, query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Run a read query with bounded SQLite lock retries."""
        for attempt in range(self._retries):
            try:
                with self.engine.connect() as connection:
                    result = connection.execute(text(query), params or {})
                    return [dict(row._mapping) for row in result]
            except OperationalError as error:
                message = str(error).lower()
                if "no such table" in message:
                    return []
                if "database is locked" in message and attempt < self._retries - 1:
                    time.sleep(self._retry_delay * (2**attempt))
                    continue
                raise
        return []

    def count(self, table_name: str) -> int:
        """Return a table count or zero when the evidence table is absent."""
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_name):
            raise ValueError("Invalid evidence table name.")
        if not self.table_exists(table_name):
            return 0
        rows = self.query(f'SELECT COUNT(*) AS cnt FROM "{table_name}"')
        return int(rows[0]["cnt"]) if rows else 0

    def integrity_status(self) -> tuple[bool, int]:
        """Return SQLite integrity and foreign-key violation evidence."""
        integrity = self.query("PRAGMA integrity_check")
        foreign_key_errors = self.query("PRAGMA foreign_key_check")
        is_valid = bool(integrity) and next(iter(integrity[0].values()), "") == "ok"
        return is_valid, len(foreign_key_errors)

    def latest_incremental_run_id(self) -> str | None:
        """Return the newest non-reconstructed ingestion-run identifier."""
        rows = self.query(
            """
            SELECT ir.id
            FROM data_ingestion_run ir
            JOIN data_source_system ss ON ss.id = ir.source_system_id
            WHERE ss.name NOT LIKE 'reconstructed/%'
            ORDER BY datetime(COALESCE(ir.finished_at, ir.started_at)) DESC
            LIMIT 1
            """
        )
        return str(rows[0]["id"]) if rows else None
