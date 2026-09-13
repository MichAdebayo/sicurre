"""Existing held items get a readable preview rebuilt from their raw MIME."""

from __future__ import annotations

from typing import Any

import pytest

from data_platform.cli.app import rebuild_quarantine_previews as rebuild

_RAW = (
    b"Received: from mail.example by cloudflare-email.net\r\n"
    b"MIME-Version: 1.0\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"Content-Transfer-Encoding: quoted-printable\r\n"
    b"\r\n"
    b"Validez vos coordonn=C3=A9es avant 72 heures.\r\n"
)


@pytest.mark.asyncio
async def test_held_items_are_rebuilt_once_and_unreadable_ones_are_counted(monkeypatch) -> None:
    rows = [
        {"id": "raw-headers", "raw_storage_uri": "r2://a", "body_text": "Received: from mail.example"},
        {"id": "already-clean", "raw_storage_uri": "r2://b", "body_text": "Validez vos coordonnées avant 72 heures."},
        {"id": "missing-object", "raw_storage_uri": "r2://c", "body_text": "x"},
    ]
    updates: list[tuple[str, tuple[Any, ...]]] = []

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if sql.startswith("SELECT"):
            assert "status = 'held'" in sql
            return rows
        updates.append((sql, params))
        return []

    class Store:
        async def read(self, uri: str) -> bytes:
            if uri == "r2://c":
                raise FileNotFoundError(uri)
            return _RAW

    monkeypatch.setattr(rebuild, "execute_runtime_query", query)
    monkeypatch.setattr(rebuild, "build_quarantine_store", lambda _settings: Store())

    counts = await rebuild.rebuild_previews()

    assert counts == {"held_with_raw": 3, "rebuilt": 1, "unchanged": 1, "failed": 1}
    assert updates == [
        (
            "UPDATE app_quarantine_item SET body_text = ? WHERE id = ? AND status = 'held'",
            ("Validez vos coordonnées avant 72 heures.", "raw-headers"),
        )
    ]


def test_main_prints_the_counts(monkeypatch, capsys) -> None:
    async def fake() -> dict[str, int]:
        return {"held_with_raw": 0, "rebuilt": 0, "unchanged": 0, "failed": 0}

    monkeypatch.setattr(rebuild, "rebuild_previews", fake)
    rebuild.main()
    assert "quarantine previews:" in capsys.readouterr().out
