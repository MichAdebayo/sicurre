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
async def test_resolve_sending_address_rejects_disabled_domain() -> None:
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


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["resolve", "send"])
async def test_cloudflare_network_failure_is_stable(operation: str) -> None:
    """Cloudflare connection failures map to one user-safe dependency error."""

    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(QuarantineDeliveryError) as exc_info:
            if operation == "resolve":
                await resolve_sending_address(api_token="token", zone_id="zone", client=client)
            else:
                await send_raw_email(
                    api_token="token",
                    account_id="account",
                    envelope_from="quarantine@example.test",
                    recipient="owner@example.test",
                    raw_mime=b"MIME",
                    client=client,
                )

    assert exc_info.value.code == "cloudflare_unreachable"


@pytest.mark.asyncio
async def test_resolve_sending_address_permission_error() -> None:
    """Envelope discovery reports a missing Email Sending permission."""
    transport = httpx.MockTransport(lambda _: httpx.Response(401, json={"success": False}))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(QuarantineDeliveryError) as exc_info:
            await resolve_sending_address(api_token="token", zone_id="zone", client=client)

    assert exc_info.value.code == "email_sending_permission_required"


@pytest.mark.asyncio
async def test_resolve_sending_address_requires_successful_response() -> None:
    """Cloudflare API errors retain their bounded provider detail."""
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            500,
            json={"errors": [{"message": "Email Sending is unavailable"}]},
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(QuarantineDeliveryError) as exc_info:
            await resolve_sending_address(api_token="token", zone_id="zone", client=client)

    assert exc_info.value.code == "cloudflare_delivery_failed"
    assert str(exc_info.value) == "Email Sending is unavailable"


@pytest.mark.asyncio
async def test_resolve_sending_address_requires_enabled_domain() -> None:
    """A successful response without an enabled domain cannot release mail."""
    transport = httpx.MockTransport(
        lambda _: httpx.Response(200, json={"success": True, "result": [{"name": "disabled.test"}]})
    )
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(QuarantineDeliveryError) as exc_info:
            await resolve_sending_address(api_token="token", zone_id="zone", client=client)

    assert exc_info.value.code == "email_sending_domain_required"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, content=b"not-json"),
        httpx.Response(200, json={"success": False, "errors": []}),
    ],
)
async def test_send_raw_email_rejects_failed_payload(response: httpx.Response) -> None:
    """HTTP and payload-level failures never masquerade as accepted delivery."""
    transport = httpx.MockTransport(lambda _: response)
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

    assert exc_info.value.code == "cloudflare_delivery_failed"


@pytest.mark.asyncio
async def test_send_raw_email_rejects_unaccepted_recipient() -> None:
    """A 200 response is insufficient unless Cloudflare accepted the recipient."""
    transport = httpx.MockTransport(
        lambda _: httpx.Response(
            200,
            json={
                "success": True,
                "result": {
                    "delivered": [],
                    "queued": [],
                    "message_id": "delivery-2",
                },
            },
        )
    )
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

    assert exc_info.value.code == "cloudflare_delivery_rejected"
