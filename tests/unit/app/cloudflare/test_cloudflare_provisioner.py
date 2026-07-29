"""Unit tests for the CloudflareProvisioner service."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from data_platform.services.cloudflare_provisioner import (
    CloudflareAPIError,
    CloudflareProvisioner,
)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, json={"error": "upstream failure"}),
        httpx.Response(403, json=[]),
        httpx.Response(200, json=[]),
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={"result": {}}),
    ],
)
def test_unwrap_rejects_http_and_contract_errors(response: httpx.Response) -> None:
    """Cloudflare failures cannot become empty successful responses."""
    with pytest.raises(CloudflareAPIError):
        CloudflareProvisioner._unwrap(response, context="contract test")


@pytest.mark.asyncio
@respx.mock
async def test_verify_token_success() -> None:
    provisioner = CloudflareProvisioner(api_token="valid-token")
    respx.get("https://api.cloudflare.com/client/v4/user/tokens/verify").mock(
        return_value=httpx.Response(200, json={"success": True, "result": {}})
    )
    assert await provisioner.verify_token() is True


@pytest.mark.asyncio
@respx.mock
async def test_verify_token_failure() -> None:
    provisioner = CloudflareProvisioner(api_token="invalid-token")
    respx.get("https://api.cloudflare.com/client/v4/user/tokens/verify").mock(
        return_value=httpx.Response(
            400,
            json={"success": False, "errors": [{"message": "Invalid token"}]},
        )
    )
    assert await provisioner.verify_token() is False


@pytest.mark.asyncio
@respx.mock
async def test_get_zone_success() -> None:
    provisioner = CloudflareProvisioner(api_token="token")
    respx.get("https://api.cloudflare.com/client/v4/zones").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "result": [
                    {
                        "id": "zone-123",
                        "account": {"id": "account-456"},
                    }
                ],
            },
        )
    )
    zone_id, account_id = await provisioner.get_zone("example.com")
    assert zone_id == "zone-123"
    assert account_id == "account-456"


@pytest.mark.asyncio
@respx.mock
async def test_get_zone_not_found() -> None:
    provisioner = CloudflareProvisioner(api_token="token")
    respx.get("https://api.cloudflare.com/client/v4/zones").mock(
        return_value=httpx.Response(200, json={"success": True, "result": []})
    )
    with pytest.raises(CloudflareAPIError) as exc_info:
        await provisioner.get_zone("example.com")
    assert "not found" in str(exc_info.value)


@pytest.mark.asyncio
@respx.mock
async def test_enable_email_routing_success() -> None:
    provisioner = CloudflareProvisioner(api_token="token")
    respx.get("https://api.cloudflare.com/client/v4/zones/zone-123/dns_records").mock(
        return_value=httpx.Response(200, json={"success": True, "result": []})
    )
    route = respx.post(
        "https://api.cloudflare.com/client/v4/zones/zone-123/email/routing/dns"
    ).mock(return_value=httpx.Response(200, json={"success": True}))
    await provisioner.enable_email_routing("zone-123")
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_enable_email_routing_already_enabled() -> None:
    provisioner = CloudflareProvisioner(api_token="token")
    respx.get("https://api.cloudflare.com/client/v4/zones/zone-123/dns_records").mock(
        return_value=httpx.Response(200, json={"success": True, "result": []})
    )
    respx.post("https://api.cloudflare.com/client/v4/zones/zone-123/email/routing/dns").mock(
        return_value=httpx.Response(
            400,
            json={"success": False, "errors": [{"message": "already enabled"}]},
        )
    )
    # Should not raise exception
    await provisioner.enable_email_routing("zone-123")


@pytest.mark.asyncio
@respx.mock
async def test_enable_email_routing_surfaces_permission_error() -> None:
    """A generic 403 is actionable and cannot masquerade as idempotent success."""
    provisioner = CloudflareProvisioner(api_token="token")
    respx.get("https://api.cloudflare.com/client/v4/zones/zone-123/dns_records").mock(
        return_value=httpx.Response(200, json={"success": True, "result": []})
    )
    respx.post("https://api.cloudflare.com/client/v4/zones/zone-123/email/routing/dns").mock(
        return_value=httpx.Response(
            403,
            json={"success": False, "errors": [{"message": "permission denied"}]},
        )
    )
    with pytest.raises(CloudflareAPIError, match="Zone Settings:Edit is required"):
        await provisioner.enable_email_routing("zone-123")


@pytest.mark.asyncio
@respx.mock
async def test_enable_email_routing_skips_existing_cloudflare_mx() -> None:
    """Existing routing DNS avoids a redundant privileged enable request."""
    provisioner = CloudflareProvisioner(api_token="token")
    respx.get("https://api.cloudflare.com/client/v4/zones/zone-123/dns_records").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "result": [
                    {"type": "MX", "content": "route1.mx.cloudflare.net", "name": "example.com"}
                ],
            },
        )
    )
    enable_route = respx.post(
        "https://api.cloudflare.com/client/v4/zones/zone-123/email/routing/dns"
    ).mock(return_value=httpx.Response(200, json={"success": True, "result": {}}))

    await provisioner.enable_email_routing("zone-123")

    assert not enable_route.called


@pytest.mark.asyncio
@respx.mock
async def test_create_destination_address_existing() -> None:
    provisioner = CloudflareProvisioner(api_token="token")
    respx.get(
        "https://api.cloudflare.com/client/v4/accounts/account-123/email/routing/addresses"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "result": [{"email": "test@dest.com", "tag": "tag-123"}],
            },
        )
    )
    tag = await provisioner.create_destination_address("account-123", "test@dest.com")
    assert tag == "tag-123"


@pytest.mark.asyncio
@respx.mock
async def test_create_destination_address_new() -> None:
    provisioner = CloudflareProvisioner(api_token="token")
    respx.get(
        "https://api.cloudflare.com/client/v4/accounts/account-123/email/routing/addresses"
    ).mock(return_value=httpx.Response(200, json={"success": True, "result": []}))
    respx.post(
        "https://api.cloudflare.com/client/v4/accounts/account-123/email/routing/addresses"
    ).mock(
        return_value=httpx.Response(
            200,
            json={"success": True, "result": {"tag": "new-tag-123"}},
        )
    )
    tag = await provisioner.create_destination_address("account-123", "new@dest.com")
    assert tag == "new-tag-123"


@pytest.mark.asyncio
@respx.mock
async def test_deploy_email_worker() -> None:
    provisioner = CloudflareProvisioner(api_token="token")
    route = respx.put(
        "https://api.cloudflare.com/client/v4/accounts/account-123/workers/scripts/my-worker"
    ).mock(return_value=httpx.Response(200, json={"success": True}))
    await provisioner.deploy_email_worker(
        account_id="account-123",
        worker_name="my-worker",
        scan_url="https://scan.test",
        shared_secret="secret",
        forward_to="forward@test.com",
    )
    assert route.called
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer token"
    assert b'"name": "SICURRE_SCAN_URL"' in request.content
    assert b'"text": "https://scan.test"' in request.content
    assert b'"type": "secret_text"' in request.content
    assert b'"text": "secret"' in request.content
    assert b'"name": "FORWARD_TO"' in request.content
    assert b'"text": "forward@test.com"' in request.content
    assert b"rawText.slice(0, 10_000)" in request.content
    assert b"replace(/Content-" not in request.content


@pytest.mark.asyncio
@respx.mock
async def test_create_email_routing_rule() -> None:
    provisioner = CloudflareProvisioner(api_token="token")
    respx.get("https://api.cloudflare.com/client/v4/zones/zone-123/email/routing/rules").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "result": [
                    {
                        "id": "old-rule-id",
                        "matchers": [{"type": "literal", "value": "target@test.com"}],
                    }
                ],
            },
        )
    )
    del_route = respx.delete(
        "https://api.cloudflare.com/client/v4/zones/zone-123/email/routing/rules/old-rule-id"
    ).mock(return_value=httpx.Response(200, json={"success": True}))
    create_route = respx.post(
        "https://api.cloudflare.com/client/v4/zones/zone-123/email/routing/rules"
    ).mock(
        return_value=httpx.Response(
            200,
            json={"success": True, "result": {"id": "new-rule-id"}},
        )
    )
    rule_id = await provisioner.create_email_routing_rule(
        "zone-123", "my-worker", "target@test.com"
    )
    assert del_route.called
    assert create_route.called
    assert rule_id == "new-rule-id"
    request = create_route.calls.last.request
    assert request.headers["Authorization"] == "Bearer token"
    payload = json.loads(request.content)
    assert payload["matchers"] == [{"type": "literal", "field": "to", "value": "target@test.com"}]
    assert payload["actions"] == [{"type": "worker", "value": ["my-worker"]}]


@pytest.mark.asyncio
@respx.mock
async def test_rule_creation_aborts_when_conflicts_cannot_be_read() -> None:
    """Provisioning cannot create duplicate rules after a failed conflict check."""
    provisioner = CloudflareProvisioner(api_token="token")
    respx.get("https://api.cloudflare.com/client/v4/zones/zone-123/email/routing/rules").mock(
        return_value=httpx.Response(
            403,
            json={"success": False, "errors": [{"message": "missing rule read"}]},
        )
    )
    create_route = respx.post(
        "https://api.cloudflare.com/client/v4/zones/zone-123/email/routing/rules"
    ).mock(return_value=httpx.Response(200, json={"success": True, "result": {}}))

    with pytest.raises(CloudflareAPIError, match="missing rule read"):
        await provisioner.create_email_routing_rule("zone-123", "my-worker", "target@test.com")
    assert not create_route.called


@pytest.mark.asyncio
@respx.mock
async def test_destination_creation_aborts_when_existing_addresses_cannot_be_read() -> None:
    """Provisioning cannot duplicate a destination after an unreadable list."""
    provisioner = CloudflareProvisioner(api_token="token")
    respx.get(
        "https://api.cloudflare.com/client/v4/accounts/account-123/email/routing/addresses"
    ).mock(
        return_value=httpx.Response(
            403,
            json={"success": False, "errors": [{"message": "missing address read"}]},
        )
    )
    create_route = respx.post(
        "https://api.cloudflare.com/client/v4/accounts/account-123/email/routing/addresses"
    ).mock(return_value=httpx.Response(200, json={"success": True, "result": {}}))

    with pytest.raises(CloudflareAPIError, match="missing address read"):
        await provisioner.create_destination_address("account-123", "target@test.com")
    assert not create_route.called


@pytest.mark.asyncio
@respx.mock
async def test_delete_worker() -> None:
    provisioner = CloudflareProvisioner(api_token="token")
    route = respx.delete(
        "https://api.cloudflare.com/client/v4/accounts/account-123/workers/scripts/my-worker"
    ).mock(return_value=httpx.Response(200, json={"success": True}))
    await provisioner.delete_worker("account-123", "my-worker")
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_delete_worker_404_ignored() -> None:
    provisioner = CloudflareProvisioner(api_token="token")
    respx.delete(
        "https://api.cloudflare.com/client/v4/accounts/account-123/workers/scripts/my-worker"
    ).mock(
        return_value=httpx.Response(
            404,
            json={"success": False, "errors": [{"message": "not found"}]},
        )
    )
    # Should not raise exception
    await provisioner.delete_worker("account-123", "my-worker")


@pytest.mark.asyncio
@respx.mock
async def test_get_email_routing_status() -> None:
    provisioner = CloudflareProvisioner(api_token="token")
    respx.get("https://api.cloudflare.com/client/v4/zones/zone-123/email/routing").mock(
        return_value=httpx.Response(
            200,
            json={"success": True, "result": {"status": "active"}},
        )
    )
    status = await provisioner.get_email_routing_status("zone-123")
    assert status == {"status": "active"}


@pytest.mark.asyncio
@respx.mock
async def test_get_dns_records() -> None:
    provisioner = CloudflareProvisioner(api_token="token")
    respx.get("https://api.cloudflare.com/client/v4/zones/zone-123/dns_records").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "result": [{"type": "MX", "name": "example.com"}],
            },
        )
    )
    records = await provisioner.get_dns_records("zone-123")
    assert records == [{"type": "MX", "name": "example.com"}]


@pytest.mark.asyncio
@respx.mock
async def test_provision_flow() -> None:
    provisioner = CloudflareProvisioner(api_token="token")

    # Mock zone resolve
    respx.get("https://api.cloudflare.com/client/v4/zones").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "result": [{"id": "zone-123", "account": {"id": "account-456"}}],
            },
        )
    )
    # Mock DNS preflight and enable routing
    respx.get("https://api.cloudflare.com/client/v4/zones/zone-123/dns_records").mock(
        return_value=httpx.Response(200, json={"success": True, "result": []})
    )
    respx.post("https://api.cloudflare.com/client/v4/zones/zone-123/email/routing/dns").mock(
        return_value=httpx.Response(200, json={"success": True})
    )
    # Mock fetching existing routing rules (return a mock literal matcher to test auto-resolve from rule)
    respx.get("https://api.cloudflare.com/client/v4/zones/zone-123/email/routing/rules").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "result": [
                    {
                        "id": "old-rule",
                        "matchers": [{"type": "literal", "value": "test@domain.com"}],
                        "actions": [{"type": "forward", "value": ["forwarded@domain.com"]}],
                    }
                ],
            },
        )
    )
    # Mock rule deletion
    respx.delete(
        "https://api.cloudflare.com/client/v4/zones/zone-123/email/routing/rules/old-rule"
    ).mock(return_value=httpx.Response(200, json={"success": True}))
    # Mock listing destination addresses (verified check)
    respx.get(
        "https://api.cloudflare.com/client/v4/accounts/account-456/email/routing/addresses"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "result": [
                    {
                        "email": "forwarded@domain.com",
                        "tag": "tag-1",
                        "status": "verified",
                    }
                ],
            },
        )
    )
    # Mock registering destination address
    respx.post(
        "https://api.cloudflare.com/client/v4/accounts/account-456/email/routing/addresses"
    ).mock(return_value=httpx.Response(200, json={"success": True, "result": {"tag": "tag-1"}}))
    # Mock worker deploy
    respx.put(
        "https://api.cloudflare.com/client/v4/accounts/account-456/workers/scripts/sicurre-gw-zone-123"
    ).mock(return_value=httpx.Response(200, json={"success": True}))
    # Mock routing rule creation
    respx.post("https://api.cloudflare.com/client/v4/zones/zone-123/email/routing/rules").mock(
        return_value=httpx.Response(200, json={"success": True, "result": {"id": "new-rule-id"}})
    )

    res = await provisioner.provision("domain.com", "test@domain.com", "https://api.test/v1/scan")
    assert res.zone_id == "zone-123"
    assert res.destination_email == "forwarded@domain.com"
    assert res.destination_verified is True


@pytest.mark.asyncio
@respx.mock
async def test_deploy_dns_record_create() -> None:
    provisioner = CloudflareProvisioner(api_token="token")
    # Mock existing DNS records
    respx.get("https://api.cloudflare.com/client/v4/zones/zone-123/dns_records").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "result": [],
            },
        )
    )
    # Mock creating new DNS record
    create_route = respx.post(
        "https://api.cloudflare.com/client/v4/zones/zone-123/dns_records"
    ).mock(return_value=httpx.Response(200, json={"success": True}))
    await provisioner.deploy_dns_record("zone-123", "TXT", "example.com", "test-content")
    assert create_route.called


@pytest.mark.asyncio
@respx.mock
async def test_deploy_dns_record_update() -> None:
    provisioner = CloudflareProvisioner(api_token="token")
    # Mock existing DNS records
    respx.get("https://api.cloudflare.com/client/v4/zones/zone-123/dns_records").mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "result": [{"id": "dns-id", "type": "TXT", "name": "example.com"}],
            },
        )
    )
    # Mock updating DNS record
    update_route = respx.put(
        "https://api.cloudflare.com/client/v4/zones/zone-123/dns_records/dns-id"
    ).mock(return_value=httpx.Response(200, json={"success": True}))
    await provisioner.deploy_dns_record("zone-123", "TXT", "example.com", "test-content")
    assert update_route.called


@pytest.mark.asyncio
@respx.mock
async def test_teardown_flow() -> None:
    provisioner = CloudflareProvisioner(api_token="token")
    # Mock delete rule
    del_rule = respx.delete(
        "https://api.cloudflare.com/client/v4/zones/zone-123/email/routing/rules/rule-123"
    ).mock(return_value=httpx.Response(200, json={"success": True}))
    # Mock delete worker
    del_worker = respx.delete(
        "https://api.cloudflare.com/client/v4/accounts/account-456/workers/scripts/my-worker"
    ).mock(return_value=httpx.Response(200, json={"success": True}))
    await provisioner.teardown("zone-123", "account-456", "my-worker", "rule-123")
    assert del_rule.called
    assert del_worker.called
