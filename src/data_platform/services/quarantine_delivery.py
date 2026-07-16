"""Cloudflare Email Service delivery for released quarantine messages."""

from __future__ import annotations

from dataclasses import dataclass
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
    zone_id: str,
    client: httpx.AsyncClient | None = None,
) -> str:
    """Return an enabled Cloudflare Email Sending envelope address."""
    request_client = client or httpx.AsyncClient(timeout=15.0)
    owns_client = client is None
    try:
        response = await request_client.get(
            f"{CF_BASE}/zones/{zone_id}/email/sending/subdomains",
            headers={"Authorization": f"Bearer {api_token}"},
        )
    except httpx.HTTPError as exc:
        raise QuarantineDeliveryError(
            "cloudflare_unreachable",
            "Cloudflare Email Sending readiness is temporarily unreachable.",
        ) from exc
    finally:
        if owns_client:
            await request_client.aclose()
    if response.status_code in {401, 403}:
        raise QuarantineDeliveryError(
            "email_sending_permission_required",
            "Cloudflare Email Sending: Edit permission is required to release messages.",
        )
    payload = _json_object(response)
    if not response.is_success:
        raise QuarantineDeliveryError("cloudflare_delivery_failed", _cloudflare_error(payload))
    result = payload.get("result") if isinstance(payload.get("result"), list) else []
    domain = next(
        (
            str(item.get("name"))
            for item in result
            if isinstance(item, dict) and item.get("enabled") and item.get("name")
        ),
        None,
    )
    if not domain:
        raise QuarantineDeliveryError(
            "email_sending_domain_required",
            "Enable a Cloudflare Email Sending domain before releasing messages.",
        )
    return f"quarantine@{domain}"


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
            "Cloudflare Email Sending: Edit permission is required to release messages.",
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
