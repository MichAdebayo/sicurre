"""
Cloudflare Email Gateway provisioner.

Automates the full setup of inbound email interception for a customer domain:
  1. Locate the Cloudflare zone for the domain
  2. Enable Email Routing on the zone
  3. Register a verified destination address (triggers CF verification email)
  4. Deploy the Sicurre Email Worker script with secret bindings
  5. Create a catch-all routing rule that pipes every inbound message to the Worker

All Cloudflare API calls use the token supplied by the user at setup time.
Secrets are never stored in plain text; only the SHA-256 hash of the worker
shared secret is persisted so the /v1/email/scan endpoint can validate requests.
"""

from __future__ import annotations

import hashlib
import json
import logging
import secrets
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

CF_BASE = "https://api.cloudflare.com/client/v4"

# ---------------------------------------------------------------------------
# Embedded Cloudflare Email Worker script
# ---------------------------------------------------------------------------
_WORKER_JS = """\
/**
 * Sicurre Email Gateway Worker
 *
 * Flow:
 *   1. Extract sender, subject and body from the inbound email
 *   2. POST to Sicurre scan endpoint (SICURRE_SCAN_URL)
 *   3. If quarantined, upload the original MIME for controlled release
 *   4. If verdict == "phishing"  → reject the message
 *   5. Otherwise                 → forward to FORWARD_TO with X-Sicurre trace headers
 *
 * Environment bindings (set via Cloudflare Workers secrets):
 *   SICURRE_SCAN_URL      – e.g. https://api.yourdomain.com/v1/email/scan
 *   SICURRE_SHARED_SECRET – random secret shared between Worker and API
 *   FORWARD_TO            – verified destination address
 */
export default {
  async email(message, env, _ctx) {
    const from    = message.from    || '';
    const subject = message.headers.get('subject') || message.headers.get('Subject') || '';

    // Read the original MIME once. Only a short text projection is classified.
    let rawBytes = new ArrayBuffer(0);
    let bodyText = '';
    try {
      rawBytes = await new Response(message.raw).arrayBuffer();
      const rawText = new TextDecoder('utf-8', { fatal: false }).decode(rawBytes);
      // Strip MIME boundary/header noise so the model gets cleaner text
      bodyText = rawText
        .replace(/--[A-Za-z0-9_\\-\\.]+(?:--)?/g, '')
        .replace(/Content-[^\\n]+\\n/g, '')
        .replace(/\\r\\n\\r\\n/g, '\\n\\n')
        .trim()
        .slice(0, 5_500);
    } catch (_) { /* fail-open body read */ }

    const headerMessageId = message.headers.get('message-id') || message.headers.get('Message-ID') || '';
    let messageId = headerMessageId.trim();
    if (!messageId && rawBytes.byteLength) {
      const digest = await crypto.subtle.digest('SHA-256', rawBytes);
      messageId = Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('');
    }

    // ── Call Sicurre scan endpoint ──────────────────────────────────────────
    let verdict = 'safe';
    let scanStatus = 'unavailable';
    let confidence = '';
    let scanHttpStatus = '';
    let quarantineId = '';
    let eventId = '';
    try {
      const resp = await fetch(env.SICURRE_SCAN_URL, {
        method : 'POST',
        headers: {
          'Content-Type'     : 'application/json',
          'X-Sicurre-Secret' : env.SICURRE_SHARED_SECRET,
        },
        body  : JSON.stringify({
          message_id     : messageId,
          subject,
          sender         : from,
          text           : bodyText,
          use_llm        : true,
          use_virustotal : false,   // skip VT on the intercept path for speed
        }),
        signal: AbortSignal.timeout(10_000),
      });
      scanHttpStatus = String(resp.status);
      if (resp.ok) {
        const data = await resp.json();
        verdict = (data.verdict || 'safe').toLowerCase();
        scanStatus = 'scanned';
        confidence = data.score === undefined ? '' : String(data.score);
        quarantineId = data.quarantine_id ? String(data.quarantine_id) : '';
        eventId = data.event_id ? String(data.event_id) : '';
      } else {
        scanStatus = 'api-error';
      }
    } catch (_) {
      scanStatus = 'api-unreachable';
      // Preserve mail availability, but never claim the message was scanned.
    }

    if (verdict === 'phishing') {
      message.setReject('Phishing email blocked by Sicurre Anti-Phishing Gateway');
      return;
    }

    if (verdict === 'quarantine') {
      if (!quarantineId || !rawBytes.byteLength) {
        message.setReject('Sicurre quarantine storage unavailable; message was not discarded');
        return;
      }
      const uploadUrl = env.SICURRE_SCAN_URL.replace(/\\/v1\\/email\\/scan\\/?$/, `/v1/email/quarantine/${quarantineId}/content`);
      try {
        const upload = await fetch(uploadUrl, {
          method: 'PUT',
          headers: {
            'Content-Type': 'message/rfc822',
            'X-Sicurre-Secret': env.SICURRE_SHARED_SECRET,
          },
          body: rawBytes,
          signal: AbortSignal.timeout(15_000),
        });
        if (!upload.ok) {
          message.setReject('Sicurre quarantine storage failed; message was not discarded');
        }
      } catch (_) {
        message.setReject('Sicurre quarantine storage unreachable; message was not discarded');
      }
      return;
    }

    // Forward clean/spam mail to the verified destination inbox.
    // X-* headers are intentionally added so fail-open delivery remains visible
    // in the destination mailbox headers when the scan API is unavailable.
    const traceHeaders = new Headers();
    traceHeaders.set('X-Sicurre-Gateway', 'cloudflare-email-worker');
    traceHeaders.set('X-Sicurre-Scan-Status', scanStatus);
    traceHeaders.set('X-Sicurre-Verdict', verdict);
    traceHeaders.set('X-Sicurre-Scan-Http-Status', scanHttpStatus);
    traceHeaders.set('X-Sicurre-Confidence', confidence);
    traceHeaders.set('X-Sicurre-Event-ID', eventId);
    await message.forward(env.FORWARD_TO, traceHeaders);
  },
};
"""


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------
@dataclass
class ProvisioningResult:
    zone_id: str
    zone_name: str
    account_id: str
    worker_name: str
    rule_id: str
    destination_email: str
    shared_secret_hash: str  # SHA-256 hex – store in DB
    shared_secret_plain: str = field(repr=False)  # used once then discarded
    destination_verified: bool = False
    message: str = (
        "Provisioning complete. Check inbox for Cloudflare verification email."
    )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# CloudflareProvisioner
# ---------------------------------------------------------------------------
class CloudflareProvisioner:
    """
    Thin async wrapper around the Cloudflare REST API.

    Instantiate with the user-supplied API token; all calls use that token.
    """

    def __init__(self, api_token: str) -> None:
        if not api_token:
            raise ValueError("Cloudflare API token must not be empty")
        self._token = api_token
        self._headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

    # ── low-level helpers ───────────────────────────────────────────────────

    async def _get(self, path: str, **kw: Any) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(f"{CF_BASE}{path}", headers=self._headers, **kw)
        return self._unwrap(r, context=f"GET {path}")

    async def _post(
        self, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.post(
                f"{CF_BASE}{path}", headers=self._headers, json=body or {}
            )
        return self._unwrap(r, context=f"POST {path}")

    async def _post_multipart(self, path: str, files: dict) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._token}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.put(f"{CF_BASE}{path}", headers=headers, files=files)
        return self._unwrap(r, context=f"PUT {path}")

    async def _delete(self, path: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.delete(f"{CF_BASE}{path}", headers=self._headers)
        return self._unwrap(r, context=f"DELETE {path}")

    @staticmethod
    def _unwrap(r: httpx.Response, *, context: str = "Cloudflare API") -> dict[str, Any]:
        try:
            data = r.json()
        except Exception:
            r.raise_for_status()
            return {}
        if not isinstance(data, dict):
            return {}
        if not data.get("success", True):
            errors = data.get("errors", [])
            msg = "; ".join(e.get("message", str(e)) for e in errors) or r.text
            raise CloudflareAPIError(f"{context}: {msg}", status_code=r.status_code)
        res: dict[str, Any] = data
        return res

    # ── public API ──────────────────────────────────────────────────────────

    async def verify_token(self) -> bool:
        """Check the token is valid and has sufficient permissions."""
        try:
            await self._get("/user/tokens/verify")
            return True
        except CloudflareAPIError:
            return False

    async def get_zone(self, zone_name: str) -> tuple[str, str]:
        """Return (zone_id, account_id) for the given domain name."""
        # Note: _get doesn't take params directly, pass via query string
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(
                f"{CF_BASE}/zones",
                headers=self._headers,
                params={"name": zone_name, "per_page": 5},
            )
        data = self._unwrap(r, context="GET /zones")
        results: list[dict] = data.get("result", [])
        if not results:
            raise CloudflareAPIError(
                f"Zone '{zone_name}' not found. "
                "Verify the domain is on this Cloudflare account and the token has DNS/Email read access."
            )
        zone = results[0]
        zone_id = zone["id"]
        account_id = zone["account"]["id"]
        logger.info("Found zone %s → id=%s  account=%s", zone_name, zone_id, account_id)
        return zone_id, account_id

    async def enable_email_routing(self, zone_id: str) -> None:
        """Enable Email Routing for a zone (idempotent)."""
        try:
            await self._post(f"/zones/{zone_id}/email/routing/enable")
            logger.info("Email Routing enabled on zone %s", zone_id)
        except CloudflareAPIError as exc:
            # CF returns an error if already enabled or if we lack permissions to modify it (but it might be already active); treat as success
            if (
                "already enabled" in str(exc).lower()
                or "authentication error" in str(exc).lower()
                or exc.status_code in {400, 403}
            ):
                logger.info(
                    "Email Routing already enabled or permission restricted on zone %s (skipped)", zone_id
                )
            else:
                raise

    async def create_destination_address(self, account_id: str, email: str) -> str:
        """
        Register a destination email address.
        Cloudflare will send a verification email to that address.
        Returns the destination address `tag` for tracking.
        """
        try:
            # Check if already exists in registered list
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.get(
                    f"{CF_BASE}/accounts/{account_id}/email/routing/addresses",
                    headers=self._headers,
                )
            addresses_data = self._unwrap(
                r, context=f"GET /accounts/{account_id}/email/routing/addresses"
            )
            for addr in addresses_data.get("result", []):
                if str(addr.get("email")).lower() == email.lower():
                    logger.info("Destination address %s already registered (tag=%s)", email, addr["tag"])
                    return str(addr["tag"])
        except Exception as exc:
            logger.warning("Could not list destination addresses: %s", exc)

        data = await self._post(
            f"/accounts/{account_id}/email/routing/addresses",
            body={"email": email},
        )
        result = data.get("result", {})
        tag = result.get("tag") or result.get("id") or email
        logger.info("Destination address %s registered (tag=%s)", email, tag)
        return str(tag)

    async def deploy_email_worker(
        self,
        account_id: str,
        worker_name: str,
        scan_url: str,
        shared_secret: str,
        forward_to: str,
    ) -> None:
        """
        Deploy the Sicurre Email Worker script to Cloudflare Workers.

        The script handles the email event, calls the scan API, and either
        forwards clean mail or rejects phishing.
        """
        metadata = {
            "main_module": "worker.js",
            "compatibility_date": "2024-12-01",
            "bindings": [
                {"type": "plain_text", "name": "SICURRE_SCAN_URL", "text": scan_url},
                {
                    "type": "secret_text",
                    "name": "SICURRE_SHARED_SECRET",
                    "text": shared_secret,
                },
                {"type": "plain_text", "name": "FORWARD_TO", "text": forward_to},
            ],
        }
        files = {
            "worker.js": ("worker.js", _WORKER_JS, "application/javascript+module"),
            "metadata": ("metadata.json", json.dumps(metadata), "application/json"),
        }
        headers = {"Authorization": f"Bearer {self._token}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.put(
                f"{CF_BASE}/accounts/{account_id}/workers/scripts/{worker_name}",
                headers=headers,
                files=files,
            )
        self._unwrap(
            r, context=f"PUT /accounts/{account_id}/workers/scripts/{worker_name}"
        )
        logger.info("Worker '%s' deployed to account %s", worker_name, account_id)

    async def create_email_routing_rule(
        self,
        zone_id: str,
        worker_name: str,
        target_email: str,
        rule_name: str = "Sicurre Intercept",
    ) -> str:
        """
        Create a specific Email Routing rule that routes inbound mail for target_email
        to the Sicurre Email Worker, deleting any conflicting existing rules first.
        """
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        
        # 1. Fetch and clean up conflicting rules matching target_email
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.get(
                    f"{CF_BASE}/zones/{zone_id}/email/routing/rules",
                    headers=headers,
                )
            rules_data = self._unwrap(
                r, context=f"GET /zones/{zone_id}/email/routing/rules"
            )
            for rule in rules_data.get("result", []):
                matchers = rule.get("matchers", [])
                for m in matchers:
                    if (
                        m.get("type") == "literal"
                        and str(m.get("value")).lower() == target_email.lower()
                    ):
                        logger.info("Deleting conflicting rule %s for %s", rule["id"], target_email)
                        await self.delete_email_rule(zone_id, rule["id"])
        except Exception as exc:
            logger.warning("Could not check/clean conflicting rules: %s", exc)

        # 2. Create the new Worker-based routing rule
        body = {
            "name": rule_name,
            "enabled": True,
            "matchers": [{"type": "literal", "field": "to", "value": target_email}],
            "actions": [{"type": "worker", "value": [worker_name]}],
            "priority": 0,
        }
        data = await self._post(f"/zones/{zone_id}/email/routing/rules", body=body)
        rule_id = (
            data.get("result", {}).get("id")
            or data.get("result", {}).get("tag")
            or "unknown"
        )
        logger.info("Email routing rule created (id=%s) for %s", rule_id, target_email)
        return str(rule_id)

    async def delete_email_rule(self, zone_id: str, rule_id: str) -> None:
        await self._delete(f"/zones/{zone_id}/email/routing/rules/{rule_id}")
        logger.info("Email routing rule %s deleted", rule_id)

    async def delete_worker(self, account_id: str, worker_name: str) -> None:
        try:
            await self._delete(f"/accounts/{account_id}/workers/scripts/{worker_name}")
            logger.info("Worker '%s' deleted", worker_name)
        except CloudflareAPIError as exc:
            if exc.status_code == 404:
                logger.info("Worker '%s' not found (already deleted)", worker_name)
            else:
                raise

    async def get_email_routing_status(self, zone_id: str) -> dict[str, Any]:
        """Return current Email Routing status for a zone."""
        data = await self._get(f"/zones/{zone_id}/email/routing")
        res = data.get("result", {})
        return res if isinstance(res, dict) else {}

    async def get_dns_records(self, zone_id: str) -> list[dict[str, Any]]:
        """Fetch all DNS records for a given zone."""
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(
                f"{CF_BASE}/zones/{zone_id}/dns_records",
                headers=self._headers,
                params={"per_page": 100},
            )
        data = self._unwrap(r, context=f"GET /zones/{zone_id}/dns_records")
        res = data.get("result", [])
        return res if isinstance(res, list) else []

    # ── full provisioning flow ──────────────────────────────────────────────

    async def provision(
        self,
        zone_name: str,
        destination_email: str,
        scan_url: str,
    ) -> ProvisioningResult:
        """
        Run the complete provisioning sequence.

        Args:
            zone_name:         Domain to protect, e.g. ``vinse.app``.
            destination_email: Where clean mail should be forwarded.
            scan_url:          Public URL of the Sicurre scan endpoint.

        Returns:
            ProvisioningResult with all IDs needed for status tracking.
        """
        # 1. Resolve zone
        zone_id, account_id = await self.get_zone(zone_name)

        # 2. Enable Email Routing
        await self.enable_email_routing(zone_id)

        target_email = destination_email
        actual_forward_to = target_email  # fallback

        # Attempt to auto-resolve actual forwarding destination from existing rules before we touch anything
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.get(
                    f"{CF_BASE}/zones/{zone_id}/email/routing/rules",
                    headers=self._headers,
                )
            rules_data = self._unwrap(
                r, context=f"GET /zones/{zone_id}/email/routing/rules"
            )
            for rule in rules_data.get("result", []):
                matchers = rule.get("matchers", [])
                for m in matchers:
                    if (
                        m.get("type") == "literal"
                        and str(m.get("value")).lower() == target_email.lower()
                    ):
                        actions = rule.get("actions", [])
                        for a in actions:
                            if a.get("type") == "forward" and a.get("value"):
                                val = a["value"]
                                if isinstance(val, list) and val:
                                    actual_forward_to = str(val[0])
                                    logger.info("Auto-resolved destination email from old rule: %s", actual_forward_to)
                                    break
        except Exception as exc:
            logger.warning("Could not auto-resolve forwarding destination from rules: %s", exc)

        # If it matches target_email itself, check verified destination addresses list for safety
        if actual_forward_to.lower() == target_email.lower():
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    r = await client.get(
                        f"{CF_BASE}/accounts/{account_id}/email/routing/addresses",
                        headers=self._headers,
                    )
                addresses_data = self._unwrap(
                    r, context=f"GET /accounts/{account_id}/email/routing/addresses"
                )
                for addr in addresses_data.get("result", []):
                    if addr.get("status") == "verified":
                        actual_forward_to = str(addr["email"])
                        logger.info("Auto-resolved destination email from verified list: %s", actual_forward_to)
                        break
            except Exception as exc:
                logger.warning("Could not auto-resolve from verified destination list: %s", exc)

        # 3. Register destination address (user gets CF verification email)
        await self.create_destination_address(account_id, actual_forward_to)

        # 4. Generate shared secret (plain secret only used here + in Worker bindings)
        shared_secret = secrets.token_urlsafe(40)
        shared_secret_hash = _sha256(shared_secret)

        # 5. Deploy Worker
        worker_name = f"sicurre-gw-{zone_id[:8]}"
        await self.deploy_email_worker(
            account_id=account_id,
            worker_name=worker_name,
            scan_url=scan_url,
            shared_secret=shared_secret,
            forward_to=actual_forward_to,
        )

        # 6. Create email routing rule
        rule_id = await self.create_email_routing_rule(zone_id, worker_name, target_email)

        # Retrieve status of the destination to check verification
        destination_verified = False
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.get(
                    f"{CF_BASE}/accounts/{account_id}/email/routing/addresses",
                    headers=self._headers,
                )
            addresses_data = self._unwrap(
                r, context=f"GET /accounts/{account_id}/email/routing/addresses"
            )
            for addr in addresses_data.get("result", []):
                if str(addr.get("email")).lower() == actual_forward_to.lower():
                    destination_verified = addr.get("status") == "verified"
                    break
        except Exception:
            pass

        return ProvisioningResult(
            zone_id=zone_id,
            zone_name=zone_name,
            account_id=account_id,
            worker_name=worker_name,
            rule_id=rule_id,
            destination_email=actual_forward_to,
            shared_secret_hash=shared_secret_hash,
            shared_secret_plain=shared_secret,
            destination_verified=destination_verified,
        )

    async def deploy_dns_record(
        self,
        zone_id: str,
        rec_type: str,
        name: str,
        content: str,
    ) -> None:
        """Create or update a DNS record for the zone."""
        # Clean record value: remove any raw python byte literal indicators (e.g. b'...')
        content_clean = content
        if content_clean.startswith("b'") or content_clean.startswith('b"'):
            content_clean = content_clean[2:-1]

        # 1. Fetch existing records to check for duplicates
        records = await self.get_dns_records(zone_id)
        existing_id = None
        
        # Cloudflare zone names are fully qualified in responses. Normalize both side-by-side comparison
        target_name_normalized = name.lower().rstrip(".")
        for rec in records:
            if rec.get("type") == rec_type:
                rec_name_normalized = str(rec.get("name", "")).lower().rstrip(".")
                if rec_name_normalized == target_name_normalized:
                    existing_id = rec["id"]
                    break

        body = {
            "type": rec_type,
            "name": name,
            "content": content_clean,
            "ttl": 3600
        }

        if existing_id:
            logger.info("Updating existing DNS record %s (%s) with content: %s", existing_id, name, content_clean)
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.put(
                    f"{CF_BASE}/zones/{zone_id}/dns_records/{existing_id}",
                    headers=self._headers,
                    json=body,
                )
            self._unwrap(
                r, context=f"PUT /zones/{zone_id}/dns_records/{existing_id}"
            )
        else:
            logger.info("Creating new DNS record (%s) with content: %s", name, content_clean)
            async with httpx.AsyncClient(timeout=20.0) as client:
                r = await client.post(
                    f"{CF_BASE}/zones/{zone_id}/dns_records",
                    headers=self._headers,
                    json=body,
                )
            self._unwrap(r, context=f"POST /zones/{zone_id}/dns_records")

    async def teardown(
        self,
        zone_id: str,
        account_id: str,
        worker_name: str,
        rule_id: str,
    ) -> None:
        """Remove the routing rule and Worker for a previously provisioned zone."""
        if rule_id and rule_id != "unknown":
            try:
                await self.delete_email_rule(zone_id, rule_id)
            except CloudflareAPIError as exc:
                logger.warning("Could not delete routing rule %s: %s", rule_id, exc)

        await self.delete_worker(account_id, worker_name)
        logger.info("Teardown complete for zone %s", zone_id)


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------
class CloudflareAPIError(Exception):
    def __init__(self, message: str, status_code: int = 0) -> None:
        super().__init__(message)
        self.status_code = status_code
