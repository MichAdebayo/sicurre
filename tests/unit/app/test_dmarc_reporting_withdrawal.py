"""Disconnecting must stop a former customer reporting to Sicurre.

Teardown removed the Worker, the routing rule and the local records, but left
`rua=mailto:dmarc@sicurre.com` in the customer's DMARC record. A domain that
had ended its relationship with Sicurre went on mailing it aggregate reports
indefinitely, with no way for its owner to know.

What is withdrawn is only our mailbox. The policy is not touched and the record
is not deleted - including one Sicurre created outright - because a departing
customer should keep whatever protection they have.
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from data_platform.api.auth import AuthUser
from data_platform.api.routers import integrations
from data_platform.services.dns_records import merge_dmarc, withdraw_dmarc_reporting


def _user() -> AuthUser:
    return AuthUser(
        id="user-1",
        email="owner@example.test",
        display_name="Owner",
        role="owner",
        workspace_id="workspace-1",
        workspace_name="Workspace",
        is_platform_admin=False,
    )


def test_our_address_is_removed_from_a_shared_list() -> None:
    """The customer's own reporting addresses survive."""
    record = "v=DMARC1; p=reject; rua=mailto:michael@vinse.app,mailto:dmarc@sicurre.com"
    assert withdraw_dmarc_reporting(record) == (
        "v=DMARC1; p=reject; rua=mailto:michael@vinse.app"
    )


def test_order_does_not_matter() -> None:
    """Ours may sit anywhere in the list."""
    record = "v=DMARC1; p=reject; rua=mailto:dmarc@sicurre.com,mailto:michael@vinse.app"
    assert withdraw_dmarc_reporting(record) == (
        "v=DMARC1; p=reject; rua=mailto:michael@vinse.app"
    )


def test_a_reporting_tag_left_empty_is_dropped_not_blanked() -> None:
    """`rua=` with nothing after it is a malformed record."""
    record = "v=DMARC1; p=reject; rua=mailto:dmarc@sicurre.com"
    assert withdraw_dmarc_reporting(record) == "v=DMARC1; p=reject"


def test_forensic_reporting_is_withdrawn_too() -> None:
    """`ruf` carries message samples; leaving it would be worse than `rua`."""
    record = "v=DMARC1; p=reject; rua=mailto:dmarc@sicurre.com; ruf=mailto:dmarc@sicurre.com"
    assert withdraw_dmarc_reporting(record) == "v=DMARC1; p=reject"


def test_a_record_without_us_is_left_alone() -> None:
    """Nothing of ours means nothing to do - and no needless DNS write."""
    assert withdraw_dmarc_reporting("v=DMARC1; p=reject; rua=mailto:michael@vinse.app") is None
    assert withdraw_dmarc_reporting("") is None


def test_the_policy_is_never_touched() -> None:
    """Withdrawing must not weaken a domain we no longer protect."""
    for policy in ("none", "quarantine", "reject"):
        record = f"v=DMARC1; p={policy}; rua=mailto:dmarc@sicurre.com; pct=50"
        result = withdraw_dmarc_reporting(record)
        assert result is not None
        assert f"p={policy}" in result, f"policy {policy} was altered"
        assert "pct=50" in result, "an unrelated tag was dropped"


def test_a_record_sicurre_created_is_kept_not_deleted() -> None:
    """The customer keeps the protection, we just stop reading their mail."""
    created = merge_dmarc("")
    assert created == "v=DMARC1; p=reject; rua=mailto:dmarc@sicurre.com"
    assert withdraw_dmarc_reporting(created) == "v=DMARC1; p=reject"


def test_withdrawal_undoes_a_merge_exactly() -> None:
    """Round trip: what we added is what we take away, and nothing else."""
    for original in (
        "v=DMARC1; p=reject; rua=mailto:michael@vinse.app",
        "v=DMARC1; p=reject; rua=mailto:a@b.test,mailto:c@d.test; pct=100",
    ):
        merged = merge_dmarc(original)
        assert "dmarc@sicurre.com" in merged, "the merge did not add our address"
        assert withdraw_dmarc_reporting(merged) == original


def test_teardown_withdraws_before_it_forgets_the_domain() -> None:
    """Guard: the teardown path must actually call the withdrawal.

    The helper existing is not the fix; teardown using it is.
    """
    source = inspect.getsource(integrations.teardown_cloudflare)
    assert "withdraw_dmarc_reporting" in source, (
        "teardown no longer withdraws Sicurre's reporting address"
    )


@pytest.mark.asyncio
async def test_a_failed_withdrawal_is_reported_not_swallowed(monkeypatch) -> None:
    """The customer is told when they are still reporting to us.

    The Worker and routing rule are already gone by this point, so a DNS
    failure must not undo the teardown - but it must not pass silently either,
    or the customer keeps mailing Sicurre their reports believing they left.
    """
    statements: list[str] = []

    async def query(sql: str, _params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        statements.append(sql)
        if sql.startswith("SELECT * FROM cloudflare_integration"):
            return [
                {
                    "id": "integration-1",
                    "status": "active",
                    "api_token": "enc:v1:value",
                    "zone_id": "zone-1",
                    "account_id": "account-1",
                    "worker_name": "worker-1",
                    "rule_id": "rule-1",
                    "zone_name": "one.example",
                }
            ]
        return []

    class Provisioner:
        def __init__(self, api_token: str) -> None:
            pass

        async def teardown(self, **_kwargs: Any) -> None:
            return None

        async def get_dns_records(self, _zone_id: str) -> list[dict[str, str]]:
            raise TimeoutError("cloudflare unreachable")

    monkeypatch.setattr(integrations, "_ensure_tables", lambda: None)
    monkeypatch.setattr(integrations, "_async_query", query)
    monkeypatch.setattr(integrations, "decrypt_secret", lambda *_a, **_k: "secret")
    monkeypatch.setattr(integrations, "CloudflareProvisioner", Provisioner)

    response = await integrations.teardown_cloudflare(
        integrations.TeardownRequest(integration_id="integration-1"), _user()
    )

    assert response["status"] == "removed", "a DNS failure must not undo the teardown"
    assert response["dmarc_reporting_withdrawn"] is False
    assert any("DELETE FROM cloudflare_integration" in sql for sql in statements)
