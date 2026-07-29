"""Cloudflare Email Service delivery for released quarantine messages."""

from __future__ import annotations

from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from typing import Any

import httpx

CF_BASE = "https://api.cloudflare.com/client/v4"


class QuarantineDeliveryError(RuntimeError):
    """Stable delivery failure suitable for API error mapping."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    """Successful or queued Cloudflare delivery metadata."""

    message_id: str
    recipient: str
    queued: bool


async def resolve_sending_address(
    *,
    api_token: str,
    account_id: str,
    zone_id: str,
    zone_name: str,
    recipient: str,
    client: httpx.AsyncClient | None = None,
) -> str:
    """Validate a free-plan routing destination and return its envelope sender."""
    request_client = client or httpx.AsyncClient(timeout=15.0)
    owns_client = client is None
    headers = {"Authorization": f"Bearer {api_token}"}
    try:
        destination_response = await request_client.get(
            f"{CF_BASE}/accounts/{account_id}/email/routing/addresses",
            headers=headers,
        )
        rules_response = await request_client.get(
            f"{CF_BASE}/zones/{zone_id}/email/routing/rules",
            headers=headers,
        )
    except httpx.HTTPError as exc:
        raise QuarantineDeliveryError(
            "cloudflare_unreachable",
            "Cloudflare Email Routing destinations are temporarily unreachable.",
        ) from exc
    finally:
        if owns_client:
            await request_client.aclose()
    if destination_response.status_code in {401, 403} or rules_response.status_code in {401, 403}:
        raise QuarantineDeliveryError(
            "email_routing_permission_required",
            "Cloudflare denied access to Email Routing destinations. Confirm Email "
            "Routing Addresses: Read is scoped to this account.",
        )
    payload = _json_object(destination_response)
    if not destination_response.is_success:
        raise QuarantineDeliveryError("cloudflare_delivery_failed", _cloudflare_error(payload))
    result = payload.get("result") if isinstance(payload.get("result"), list) else []
    destination = next(
        (
            item
            for item in result
            if isinstance(item, dict)
            and str(item.get("email") or "").lower() == recipient.lower()
        ),
        None,
    )
    if not destination or not destination.get("verified"):
        raise QuarantineDeliveryError(
            "verified_destination_required",
            "Verify the connected destination address in Cloudflare Email Routing "
            "before releasing messages.",
        )
    rules_payload = _json_object(rules_response)
    if not rules_response.is_success:
        raise QuarantineDeliveryError(
            "cloudflare_delivery_failed", _cloudflare_error(rules_payload)
        )
    sender = _routing_sender(rules_payload, zone_name)
    if not sender:
        raise QuarantineDeliveryError(
            "email_routing_sender_required",
            "Configure an enabled literal Email Routing address on the connected domain "
            "before releasing messages.",
        )
    return sender


def prepare_restoration_mime(raw_mime: bytes, *, sender: str, recipient: str) -> bytes:
    """Rewrite delivery headers while preserving the original sender for replies."""
    message = BytesParser(policy=policy.SMTP).parsebytes(raw_mime)
    original_from = str(message.get("From") or "").strip()
    for header in (
        "From",
        "To",
        "DKIM-Signature",
        "ARC-Seal",
        "ARC-Message-Signature",
        "ARC-Authentication-Results",
        "Authentication-Results",
    ):
        while header in message:
            del message[header]
    message["From"] = f"Sicurre Restoration <{sender}>"
    message["To"] = recipient
    if original_from:
        if "Reply-To" not in message:
            message["Reply-To"] = original_from
        message["X-Sicurre-Original-From"] = original_from
    return message.as_bytes(policy=policy.SMTP)


def _routing_sender(payload: dict[str, Any], zone_name: str) -> str | None:
    """Return the first enabled literal routing address on the connected zone."""
    rules = payload.get("result") if isinstance(payload.get("result"), list) else []
    suffix = f"@{zone_name.lower()}"
    for rule in rules:
        if not isinstance(rule, dict) or not rule.get("enabled"):
            continue
        for matcher in rule.get("matchers", []):
            if not isinstance(matcher, dict) or matcher.get("type") != "literal":
                continue
            value = str(matcher.get("value") or "").lower()
            if value.endswith(suffix):
                return value
    return None


async def send_raw_email(
    *,
    api_token: str,
    account_id: str,
    envelope_from: str,
    recipient: str,
    raw_mime: bytes,
    client: httpx.AsyncClient | None = None,
) -> DeliveryResult:
    """Deliver original MIME through Cloudflare Email Service."""
    request_client = client or httpx.AsyncClient(timeout=20.0)
    owns_client = client is None
    try:
        response = await request_client.post(
            f"{CF_BASE}/accounts/{account_id}/email/sending/send_raw",
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            },
            json={
                "from": envelope_from,
                "recipients": [recipient],
                "mime_message": raw_mime.decode("utf-8", errors="replace"),
            },
        )
    except httpx.HTTPError as exc:
        raise QuarantineDeliveryError(
            "cloudflare_unreachable",
            "Cloudflare Email Service is temporarily unreachable.",
        ) from exc
    finally:
        if owns_client:
            await request_client.aclose()

    payload = _json_object(response)
    if response.status_code in {401, 403}:
        raise QuarantineDeliveryError(
            "email_sending_permission_required",
            "Cloudflare denied delivery. Confirm Email Sending: Edit is scoped to "
            "the account and the recipient is a verified Email Routing destination.",
        )
    if not response.is_success or payload.get("success") is not True:
        detail = _cloudflare_error(payload)
        raise QuarantineDeliveryError("cloudflare_delivery_failed", detail)

    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    delivered = {str(value).lower() for value in result.get("delivered", [])}
    queued = {str(value).lower() for value in result.get("queued", [])}
    normalized_recipient = recipient.lower()
    if normalized_recipient not in delivered | queued:
        raise QuarantineDeliveryError(
            "cloudflare_delivery_rejected",
            "Cloudflare did not accept the destination address for delivery.",
        )
    return DeliveryResult(
        message_id=str(result.get("message_id") or ""),
        recipient=recipient,
        queued=normalized_recipient in queued,
    )


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _cloudflare_error(payload: dict[str, Any]) -> str:
    errors = payload.get("errors")
    if isinstance(errors, list) and errors and isinstance(errors[0], dict):
        message = str(errors[0].get("message") or "").strip()
        if message:
            return message[:240]
    return "Cloudflare could not release the quarantined message."
