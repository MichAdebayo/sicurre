"""Tests for retained PhishTank API evidence."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from poc import seed_api_evidence
from poc.seed_api_evidence import load_export


def test_load_export_preserves_api_urls_as_local_payload(tmp_path: Path) -> None:
    export = tmp_path / "phishtank.json"
    export.write_text(
        json.dumps({"urls": ["https://example.fr/connexion", ""]}),
        encoding="utf-8",
    )

    payload = load_export(export)

    assert payload.entries == [{"url": "https://example.fr/connexion"}]
    assert payload.source_format == "json"
    assert payload.source_url == "https://data.phishtank.com/data/online-valid.csv"


@pytest.mark.asyncio
async def test_replay_persists_reference_only_lineage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executed: list[object] = []

    class FakeSession:
        async def __aenter__(self) -> "FakeSession":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def execute(self, statement: object) -> None:
            executed.append(statement)

        async def commit(self) -> None:
            executed.append("commit")

    class FakeEngine:
        async def dispose(self) -> None:
            executed.append("dispose")

    class FakeService:
        def __init__(self, **_kwargs: object) -> None:
            pass

        async def run(self, _session: object, **_kwargs: object) -> object:
            return SimpleNamespace(
                raw_record_count=7,
                source_system_id="12345678-1234-5678-1234-567812345678",
            )

    settings = SimpleNamespace(
        snapshot_dir=tmp_path,
        data_platform_database_url="sqlite+aiosqlite:///:memory:",
    )
    monkeypatch.setattr(seed_api_evidence, "get_poc_settings", lambda: settings)
    monkeypatch.setattr(
        seed_api_evidence,
        "load_export",
        lambda: SimpleNamespace(entries=[], snapshot_bytes=b""),
    )
    monkeypatch.setattr(seed_api_evidence, "PhishTankIngestionService", FakeService)
    monkeypatch.setattr(seed_api_evidence, "create_async_engine", lambda *_a, **_k: FakeEngine())
    monkeypatch.setattr(seed_api_evidence, "async_sessionmaker", lambda *_a, **_k: FakeSession)

    assert await seed_api_evidence.replay_api_evidence() == 7
    assert executed[-2:] == ["commit", "dispose"]


def test_main_reports_inserted_count(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(seed_api_evidence, "replay_api_evidence", lambda: _return_count())
    seed_api_evidence.main()
    assert "9 new records" in capsys.readouterr().out


async def _return_count() -> int:
    return 9
