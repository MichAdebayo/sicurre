"""Loops alert payloads match the variables each template declares."""

from __future__ import annotations

import inspect
import re

from data_platform.api.routers import app_routes, integrations

#: Retrieved from GET /api/v1/transactional on 4 September 2026.
THREAT_QUARANTINED = {
    "firstName",
    "domainName",
    "sender",
    "emailSubject",
    "riskScore",
    "interceptedAt",
    "quarantineUrl",
}
DNS_SHIELD_ALERT = {"firstName", "domainName", "dnsAnomalyDetails", "domainShieldUrl"}


def _data_variable_keys(source: str, transaction_setting: str) -> set[str]:
    """Keys of the data_variables dict in the call using that transaction id."""
    start = source.index(transaction_setting)
    block = source[start : source.index("},", start)]
    body = block[block.index("data_variables={") :]
    return set(re.findall(r'"([A-Za-z_]+)":', body))


def test_threat_quarantined_payload_matches_the_template() -> None:
    keys = _data_variable_keys(
        inspect.getsource(integrations), "loops_threat_quarantined_transaction_id"
    )
    assert keys == THREAT_QUARANTINED, (
        f"payload does not match the Loops template. "
        f"missing={THREAT_QUARANTINED - keys} unexpected={keys - THREAT_QUARANTINED}"
    )


def test_the_renamed_sender_variable_is_not_reintroduced() -> None:
    """The specific regression: senderEmail instead of sender."""
    source = inspect.getsource(integrations)
    assert '"senderEmail"' not in source, (
        "senderEmail is the old name; the template declares sender"
    )


def test_dns_shield_payload_matches_the_template() -> None:
    keys = _data_variable_keys(
        inspect.getsource(app_routes), "loops_dns_shield_alert_transaction_id"
    )
    assert keys == DNS_SHIELD_ALERT, (
        f"payload does not match the Loops template. "
        f"missing={DNS_SHIELD_ALERT - keys} unexpected={keys - DNS_SHIELD_ALERT}"
    )
