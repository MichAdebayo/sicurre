"""Unit tests for the CloudflareProvisioner service."""

from __future__ import annotations

import httpx
import pytest
import respx

from data_platform.services.cloudflare_provisioner import (
    CloudflareAPIError,
    CloudflareProvisioner,
)


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
    route = respx.post(
        "https://api.cloudflare.com/client/v4/zones/zone-123/email/routing/enable"
    ).mock(return_value=httpx.Response(200, json={"success": True}))
    await provisioner.enable_email_routing("zone-123")
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_enable_email_routing_already_enabled() -> None:
    provisioner = CloudflareProvisioner(api_token="token")
    respx.post(
        "https://api.cloudflare.com/client/v4/zones/zone-123/email/routing/enable"
    ).mock(
        return_value=httpx.Response(
            400,
            json={"success": False, "errors": [{"message": "already enabled"}]},
        )
    )
    # Should not raise exception
    await provisioner.enable_email_routing("zone-123")


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
    tag = await provisioner.create_destination_address(
        "account-123", "test@dest.com"
    )
    assert tag == "tag-123"


@pytest.mark.asyncio
@respx.mock
async def test_create_destination_address_new() -> None:
    provisioner = CloudflareProvisioner(api_token="token")
    respx.get(
        "https://api.cloudflare.com/client/v4/accounts/account-123/email/routing/addresses"
    ).mock(
        return_value=httpx.Response(200, json={"success": True, "result": []})
    )
    respx.post(
        "https://api.cloudflare.com/client/v4/accounts/account-123/email/routing/addresses"
    ).mock(
        return_value=httpx.Response(
            200,
            json={"success": True, "result": {"tag": "new-tag-123"}},
        )
    )
    tag = await provisioner.create_destination_address(
        "account-123", "new@dest.com"
    )
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


@pytest.mark.asyncio
@respx.mock
async def test_create_email_routing_rule() -> None:
    provisioner = CloudflareProvisioner(api_token="token")
    respx.get(
        "https://api.cloudflare.com/client/v4/zones/zone-123/email/routing/rules"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "result": [
                    {
                        "id": "old-rule-id",
                        "matchers": [
                            {"type": "literal", "value": "target@test.com"}
                        ],
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
    respx.get(
        "https://api.cloudflare.com/client/v4/zones/zone-123/email/routing"
    ).mock(
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
    respx.get(
        "https://api.cloudflare.com/client/v4/zones/zone-123/dns_records"
    ).mock(
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
                "result": [
                    {"id": "zone-123", "account": {"id": "account-456"}}
                ],
            },
        )
    )
    # Mock enable routing
    respx.post(
        "https://api.cloudflare.com/client/v4/zones/zone-123/email/routing/enable"
    ).mock(return_value=httpx.Response(200, json={"success": True}))
    # Mock fetching existing routing rules (return a mock literal matcher to test auto-resolve from rule)
    respx.get(
        "https://api.cloudflare.com/client/v4/zones/zone-123/email/routing/rules"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "result": [
                    {
                        "id": "old-rule",
                        "matchers": [
                            {"type": "literal", "value": "test@domain.com"}
                        ],
                        "actions": [
                            {"type": "forward", "value": ["forwarded@domain.com"]}
                        ],
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
    ).mock(
        return_value=httpx.Response(
            200, json={"success": True, "result": {"tag": "tag-1"}}
        )
    )
    # Mock worker deploy
    respx.put(
        "https://api.cloudflare.com/client/v4/accounts/account-456/workers/scripts/sicurre-gw-zone-123"
    ).mock(return_value=httpx.Response(200, json={"success": True}))
    # Mock routing rule creation
    respx.post(
        "https://api.cloudflare.com/client/v4/zones/zone-123/email/routing/rules"
    ).mock(
        return_value=httpx.Response(
            200, json={"success": True, "result": {"id": "new-rule-id"}}
        )
    )

    res = await provisioner.provision(
        "domain.com", "test@domain.com", "https://api.test/v1/scan"
    )
    assert res.zone_id == "zone-123"
    assert res.destination_email == "forwarded@domain.com"
    assert res.destination_verified is True


@pytest.mark.asyncio
@respx.mock
async def test_deploy_dns_record_create() -> None:
    provisioner = CloudflareProvisioner(api_token="token")
    # Mock existing DNS records
    respx.get(
        "https://api.cloudflare.com/client/v4/zones/zone-123/dns_records"
    ).mock(
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
    await provisioner.deploy_dns_record(
        "zone-123", "TXT", "example.com", "test-content"
    )
    assert create_route.called


@pytest.mark.asyncio
@respx.mock
async def test_deploy_dns_record_update() -> None:
    provisioner = CloudflareProvisioner(api_token="token")
    # Mock existing DNS records
    respx.get(
        "https://api.cloudflare.com/client/v4/zones/zone-123/dns_records"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "result": [
                    {"id": "dns-id", "type": "TXT", "name": "example.com"}
                ],
            },
        )
    )
    # Mock updating DNS record
    update_route = respx.put(
        "https://api.cloudflare.com/client/v4/zones/zone-123/dns_records/dns-id"
    ).mock(return_value=httpx.Response(200, json={"success": True}))
    await provisioner.deploy_dns_record(
        "zone-123", "TXT", "example.com", "test-content"
    )
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
    await provisioner.teardown(
        "zone-123", "account-456", "my-worker", "rule-123"
    )
    assert del_rule.called
    assert del_worker.called
