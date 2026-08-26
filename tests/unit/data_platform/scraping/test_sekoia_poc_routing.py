"""Tests for production and POC SEKOIA snapshot routing."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from data_platform.cron_schedulers.scraping import run_sekoia_ioc
from data_platform.cron_schedulers.scraping.run_sekoia_ioc import (
    configure_snapshot_environment,
)


def test_default_cron_uses_production_namespace() -> None:
    environ: dict[str, str] = {}
    configure_snapshot_environment(environ, reserved=False)
    assert environ["SICURRE_SEKOIA_SNAPSHOT_STORAGE_BACKEND"] == "prod"
    assert environ["SICURRE_SEKOIA_SNAPSHOT_PREFIX"] == "cron/scraping/sekoia_ioc"


def test_reserved_cron_uses_reserved_namespace() -> None:
    environ: dict[str, str] = {}
    configure_snapshot_environment(environ, reserved=True)
    assert environ["SICURRE_SEKOIA_SNAPSHOT_PREFIX"] == "cron/reserved/scraping/sekoia_ioc"


def test_poc_cron_uses_local_demonstration_namespace() -> None:
    environ = {
        "SICURRE_POC_MODE": "true",
        "SICURRE_POC_SNAPSHOT_PREFIX": "demonstrations/jury",
    }
    configure_snapshot_environment(environ, reserved=False)
    assert environ["SICURRE_SEKOIA_SNAPSHOT_STORAGE_BACKEND"] == "local"
    assert environ["SICURRE_SEKOIA_SNAPSHOT_PREFIX"] == "demonstrations/jury/scraping/sekoia_ioc"


@pytest.mark.asyncio
async def test_runner_forwards_local_snapshot_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeConnection:
        async def run_sync(self, operation: object) -> None:
            captured["schema_operation"] = operation

    class FakeEngine:
        @asynccontextmanager
        async def begin(self):
            yield FakeConnection()

        async def dispose(self) -> None:
            captured["disposed"] = True

    class FakeSession:
        async def __aenter__(self) -> FakeSession:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

    class FakeService:
        def __init__(self, *, snapshot_dir: Path | None, snapshot_prefix: str) -> None:
            captured["snapshot_dir"] = snapshot_dir
            captured["snapshot_prefix"] = snapshot_prefix

        async def run(self, session: object, *, trigger_mode: str) -> str:
            captured["session"] = session
            captured["trigger_mode"] = trigger_mode
            return "complete"

    monkeypatch.setenv("SICURRE_POC_SNAPSHOT_DIR", "/tmp/poc-snapshots")
    monkeypatch.setattr(
        run_sekoia_ioc,
        "get_settings",
        lambda: SimpleNamespace(
            data_platform_database_url="sqlite+aiosqlite:///:memory:",
            sekoia_snapshot_prefix="demonstrations/poc/scraping/sekoia_ioc",
        ),
    )
    monkeypatch.setattr(run_sekoia_ioc, "create_async_engine", lambda *args, **kwargs: FakeEngine())
    monkeypatch.setattr(run_sekoia_ioc, "async_sessionmaker", lambda *args, **kwargs: FakeSession)
    monkeypatch.setattr(run_sekoia_ioc, "SekoiaIocIngestionService", FakeService)

    assert await run_sekoia_ioc.run_ingestion(trigger_mode="poc_demo") == "complete"
    assert captured["snapshot_dir"] == Path("/tmp/poc-snapshots")
    assert captured["snapshot_prefix"] == "demonstrations/poc/scraping/sekoia_ioc"
    assert captured["trigger_mode"] == "poc_demo"
    assert captured["disposed"] is True


@pytest.mark.asyncio
async def test_main_reports_selected_snapshot_route(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("SICURRE_SEKOIA_SNAPSHOT_PREFIX", "demonstrations/poc/sekoia")
    monkeypatch.setenv("SICURRE_SEKOIA_SNAPSHOT_STORAGE_BACKEND", "local")

    async def fake_run_ingestion(*, trigger_mode: str) -> str:
        assert trigger_mode == "scheduled"
        return "complete"

    monkeypatch.setattr(run_sekoia_ioc, "run_ingestion", fake_run_ingestion)
    with caplog.at_level("INFO"):
        await run_sekoia_ioc.main()

    assert "snapshot backend: local" in caplog.text
    assert "demonstrations/poc/sekoia" in caplog.text
