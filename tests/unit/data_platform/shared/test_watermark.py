from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql, sqlite

from data_platform.services.shared.watermark import WatermarkService


class RecordingSession:
    """Minimal async-session double that records the generated statement."""

    def __init__(self, dialect: Any, result: str | None = None) -> None:
        self._bind = SimpleNamespace(dialect=dialect)
        self.result = result
        self.statement: Any = None

    def get_bind(self) -> Any:
        return self._bind

    async def scalar(self, statement: Any) -> str | None:
        self.statement = statement
        return self.result


@pytest.mark.asyncio
async def test_json_watermark_uses_sqlite_json_extract() -> None:
    session = RecordingSession(sqlite.dialect(), "2026-08-09T00:00:00+00:00")

    result = await WatermarkService.get_max_json_field_date(
        session, "phishtank-online-valid", "$.submission_time"
    )

    sql = str(session.statement.compile(dialect=sqlite.dialect()))
    assert "json_extract" in sql.lower()
    assert result == "2026-08-09T00:00:00+00:00"


@pytest.mark.asyncio
async def test_json_watermark_uses_postgresql_json_operator() -> None:
    session = RecordingSession(postgresql.dialect(), "2026-08-09T00:00:00+00:00")

    result = await WatermarkService.get_max_json_field_date(
        session, "phishtank-online-valid", "$.submission_time"
    )

    sql = str(session.statement.compile(dialect=postgresql.dialect()))
    assert "->>" in sql
    assert "json_extract" not in sql.lower()
    assert result == "2026-08-09T00:00:00+00:00"


@pytest.mark.asyncio
async def test_json_watermark_rejects_unsupported_paths() -> None:
    session = RecordingSession(sqlite.dialect())

    with pytest.raises(ValueError, match="root JSON field"):
        await WatermarkService.get_max_json_field_date(
            session, "phishtank-online-valid", "$.nested.submission_time"
        )
