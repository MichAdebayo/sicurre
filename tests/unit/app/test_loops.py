from __future__ import annotations

from typing import Any

import httpx
import pytest

from core.config import Settings
from core.loops import LOOPS_TRANSACTIONAL_URL, send_loops_transactional


@pytest.mark.asyncio
async def test_loops_skips_missing_configuration(monkeypatch) -> None:
    monkeypatch.setattr(
        "core.loops.get_settings", lambda: Settings(_env_file=None, loops_api_key=None)
    )

    assert await send_loops_transactional("user@example.test", "template", {}) is False

    settings = Settings(_env_file=None).model_copy(update={"loops_api_key": "key"})
    monkeypatch.setattr("core.loops.get_settings", lambda: settings)
    assert await send_loops_transactional("user@example.test", None, {}) is False


@pytest.mark.asyncio
@pytest.mark.parametrize(("status_code", "expected"), [(200, True), (201, True), (400, False)])
async def test_loops_maps_provider_status(monkeypatch, status_code: int, expected: bool) -> None:
    captured: dict[str, Any] = {}

    class Client:
        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *_: Any) -> None:
            return None

        async def post(self, url: str, **kwargs: Any) -> httpx.Response:
            captured.update(url=url, **kwargs)
            return httpx.Response(status_code, text="provider response")

    monkeypatch.setattr("core.loops.httpx.AsyncClient", lambda **_: Client())
    settings = Settings(_env_file=None).model_copy(update={"loops_api_key": "key"})
    monkeypatch.setattr("core.loops.get_settings", lambda: settings)

    result = await send_loops_transactional("user@example.test", "template", {"name": "Ada"})

    assert result is expected
    assert captured["url"] == LOOPS_TRANSACTIONAL_URL
    assert captured["json"]["transactionalId"] == "template"
    assert captured["headers"]["Authorization"] == "Bearer key"


@pytest.mark.asyncio
async def test_loops_handles_transport_exception(monkeypatch) -> None:
    class Client:
        async def __aenter__(self) -> Client:
            raise httpx.ConnectError("offline")

        async def __aexit__(self, *_: Any) -> None:
            return None

    monkeypatch.setattr("core.loops.httpx.AsyncClient", lambda **_: Client())
    monkeypatch.setattr(
        "core.loops.get_settings", lambda: Settings(_env_file=None, loops_api_key="key")
    )

    assert await send_loops_transactional("user@example.test", "template", {}) is False
