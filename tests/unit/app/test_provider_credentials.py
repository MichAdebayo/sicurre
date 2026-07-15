"""Provider credential migration tests."""

from __future__ import annotations

import base64
from typing import Any

import pytest

from core.config import Settings
from core.provider_credentials import encrypt_legacy_provider_credentials

TEST_KEY = base64.urlsafe_b64encode(b"k" * 32).decode("ascii")


@pytest.mark.asyncio
async def test_legacy_provider_tokens_are_encrypted_idempotently(monkeypatch) -> None:
    """Startup migration rewrites plaintext without exposing it or touching ciphertext."""
    writes: list[tuple[str, tuple[Any, ...]]] = []

    async def query(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        if sql.startswith("SELECT id"):
            return [
                {"id": "cf-1", "workspace_id": "ws-1", "api_token": "plaintext-token"},
                {"id": "cf-2", "workspace_id": "ws-2", "api_token": "enc:v1:already"},
            ]
        if sql.startswith("SELECT workspace_id"):
            return [{"workspace_id": "ws-1", "api_token": "second-plaintext"}]
        writes.append((sql, params))
        return []

    monkeypatch.setattr("core.provider_credentials.execute_runtime_query", query)
    settings = Settings(
        _env_file=None,
        environment="production",
        secret_encryption_key=TEST_KEY,
    )

    assert await encrypt_legacy_provider_credentials(settings) == 2
    assert len(writes) == 2
    assert all(str(params[0]).startswith("enc:v1:") for _, params in writes)
    assert all("plaintext" not in str(params[0]) for _, params in writes)
    assert "workspace_id = ?" in writes[0][0]
