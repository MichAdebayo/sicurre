"""Quarantine custody and Cloudflare delivery contract tests."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from data_platform.services.quarantine_delivery import (
    QuarantineDeliveryError,
    resolve_sending_address,
    send_raw_email,
)
from data_platform.services.quarantine_storage import LocalQuarantineStore


@pytest.mark.asyncio
async def test_local_quarantine_store_round_trip_and_delete(tmp_path: Path) -> None:
    """Local custody preserves bytes and supports privacy deletion."""
    store = LocalQuarantineStore(tmp_path)
    payload = b"From: sender@example.test\r\nSubject: Invoice\r\n\r\nBody"

    stored = await store.write(workspace_id="workspace", item_id="item", payload=payload)

    assert stored.content_hash
    assert stored.size_bytes == len(payload)
    assert await store.read(stored.storage_uri) == payload
    await store.delete(stored.storage_uri)
    assert not Path(stored.storage_uri.removeprefix("file://")).exists()


@pytest.mark.asyncio
async def test_cloudflare_raw_delivery_accepts_queued_recipient() -> None:
    """Queued delivery is a successful handoff with a stable message identifier."""

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer token"
        assert request.url.path.endswith("/email/sending/send_raw")
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": {
                    "delivered": [],
                    "queued": ["owner@example.test"],
                    "permanent_bounces": [],
                    "message_id": "delivery-1",
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await send_raw_email(
            api_token="token",
            account_id="account",
            envelope_from="quarantine@example.test",
            recipient="owner@example.test",
            raw_mime=b"From: original@example.net\r\n\r\nBody",
            client=client,
        )

    assert result.message_id == "delivery-1"
    assert result.queued is True


@pytest.mark.asyncio
async def test_resolve_sending_address_requires_enabled_domain() -> None:
    """Release envelopes use a domain Cloudflare reports as enabled."""
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200,
            json={"success": True, "result": [{"name": "mail.example.test", "enabled": True}]},
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        address = await resolve_sending_address(
            api_token="token",
            zone_id="zone",
            client=client,
        )

    assert address == "quarantine@mail.example.test"


@pytest.mark.asyncio
async def test_cloudflare_permission_error_is_actionable() -> None:
    """A missing Email Sending grant is distinguishable from an outage."""
    transport = httpx.MockTransport(lambda _: httpx.Response(403, json={"success": False}))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(QuarantineDeliveryError) as exc_info:
            await send_raw_email(
                api_token="token",
                account_id="account",
                envelope_from="quarantine@example.test",
                recipient="owner@example.test",
                raw_mime=b"MIME",
                client=client,
            )

    assert exc_info.value.code == "email_sending_permission_required"
