"""Server-only persistence helpers for provider API credentials."""

from __future__ import annotations

from core.config import Settings
from core.secret_cipher import encrypt_secret
from db.runtime import execute_runtime_query


async def encrypt_legacy_provider_credentials(settings: Settings) -> int:
    """Idempotently encrypt plaintext Cloudflare credentials left by older releases."""
    migrated = 0
    integration_rows = await execute_runtime_query(
        "SELECT id, workspace_id, api_token FROM cloudflare_integration "
        "WHERE api_token IS NOT NULL AND api_token != ''"
    )
    for row in integration_rows:
        token = str(row["api_token"])
        encrypted = encrypt_secret(
            token,
            configured_key=settings.secret_encryption_key,
            environment=settings.environment,
        )
        if encrypted == token:
            continue
        await execute_runtime_query(
            "UPDATE cloudflare_integration SET api_token = ? "
            "WHERE id = ? AND workspace_id = ?",
            (encrypted, row["id"], row["workspace_id"]),
        )
        migrated += 1

    config_rows = await execute_runtime_query(
        "SELECT workspace_id, api_token FROM app_cloudflare_config "
        "WHERE api_token IS NOT NULL AND api_token != ''"
    )
    for row in config_rows:
        token = str(row["api_token"])
        encrypted = encrypt_secret(
            token,
            configured_key=settings.secret_encryption_key,
            environment=settings.environment,
        )
        if encrypted == token:
            continue
        await execute_runtime_query(
            "UPDATE app_cloudflare_config SET api_token = ? WHERE workspace_id = ?",
            (encrypted, row["workspace_id"]),
        )
        migrated += 1
    return migrated
