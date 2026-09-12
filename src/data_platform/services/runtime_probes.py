"""Runtime probes behind the platform admin health page.

Each probe reports components as ``{"component", "status", "message", ...}``
dicts; ``component_rollup`` folds them into one status. ``quiet_rows`` and
``quiet_count`` are the queries a status page tolerates failing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from core.config import get_settings
from core.secret_cipher import decrypt_secret
from data_platform.services.quarantine_storage import build_quarantine_store
from db.runtime import execute_runtime_query

logger = logging.getLogger(__name__)


CF_BASE = "https://api.cloudflare.com/client/v4"


async def quiet_count(sql: str, params: tuple = ()) -> int:
    try:
        rows = await execute_runtime_query(sql, params)
        return int(rows[0]["count"]) if rows else 0
    except Exception:
        return 0


async def quiet_rows(sql: str, params: tuple = ()) -> list[dict]:
    try:
        return await execute_runtime_query(sql, params)
    except Exception:
        return []


def _runtime_status(
    *,
    component: str,
    status: str,
    message: str,
    detail: str | None = None,
    checked_url: str | None = None,
    latency_ms: int | None = None,
) -> dict:
    return {
        "component": component,
        "status": status,
        "message": message,
        "detail": detail,
        "checked_url": checked_url,
        "latency_ms": latency_ms,
    }


def component_rollup(components: list[dict]) -> str:
    statuses = {component["status"] for component in components}
    if "down" in statuses:
        return "down"
    if "degraded" in statuses:
        return "degraded"
    if "unknown" in statuses:
        return "unknown"
    return "ok"


def _http_latency_ms(started_at: datetime) -> int:
    return int((datetime.now(timezone.utc) - started_at).total_seconds() * 1000)


async def probe_inference_runtime(
    client: httpx.AsyncClient, inference_url: str | None, api_key: str | None = None
) -> list[dict]:
    if not inference_url:
        return [
            _runtime_status(
                component="inference_api",
                status="down",
                message="SICURRE_INFERENCE_API_URL is not configured.",
            )
        ]

    base_url = inference_url.rsplit("/v1/classify", 1)[0].rstrip("/")
    health_url = f"{base_url}/v1/health"
    ready_url = f"{base_url}/v1/ready"
    results = []
    for name, url in (("inference_health", health_url), ("inference_ready", ready_url)):
        started = datetime.now(timezone.utc)
        try:
            response = await client.get(url)
            latency = _http_latency_ms(started)
            results.append(
                _runtime_status(
                    component=name,
                    status="ok" if response.status_code == 200 else "degraded",
                    message=f"{response.status_code} response from deployed classifier.",
                    checked_url=url,
                    latency_ms=latency,
                )
            )
        except Exception as exc:
            results.append(
                _runtime_status(
                    component=name,
                    status="down",
                    message="Classifier endpoint is unreachable.",
                    detail=str(exc)[:220],
                    checked_url=url,
                )
            )

    results.append(await probe_inference_contract(client, inference_url, api_key))
    return results


_PROBE_PAYLOAD = {
    "subject": "SICURRE-RUNTIME-PROBE",
    "sender": "probe@sicurre.invalid",
    "text": "Synthetic runtime probe. Not a client message.",
    # The probe establishes the auth contract and the model path.
    "use_llm": False,
    "use_virustotal": False,
}


async def probe_inference_contract(
    client: httpx.AsyncClient, inference_url: str, api_key: str | None
) -> dict:
    """Authenticated call to /v1/classify — the check incident 06 was missing."""
    if not api_key:
        return _runtime_status(
            component="inference_contract",
            status="down",
            message="SICURRE_INFERENCE_API_KEY is not configured.",
            detail="The classifier is reachable but the API would send an empty bearer token.",
            checked_url=inference_url,
        )

    started = datetime.now(timezone.utc)
    try:
        response = await client.post(
            inference_url,
            json=_PROBE_PAYLOAD,
            headers={"Authorization": f"Bearer {api_key}"},
        )
    except Exception as exc:
        return _runtime_status(
            component="inference_contract",
            status="down",
            message="Authenticated classification probe could not reach the classifier.",
            detail=str(exc)[:220],
            checked_url=inference_url,
        )

    latency = _http_latency_ms(started)

    if response.status_code in (401, 403):
        return _runtime_status(
            component="inference_contract",
            status="down",
            message="Classifier rejected the API credentials.",
            detail=(
                f"HTTP {response.status_code}. The key is present but not accepted; "
                "health and readiness stay green because they need no credentials."
            ),
            checked_url=inference_url,
            latency_ms=latency,
        )

    if response.status_code != 200:
        return _runtime_status(
            component="inference_contract",
            status="degraded",
            message=f"Authenticated probe returned HTTP {response.status_code}.",
            checked_url=inference_url,
            latency_ms=latency,
        )

    # A 200 carrying no verdict means the route answered without classifying,
    # which is the same operational outcome as a refusal.
    try:
        verdict = (response.json() or {}).get("verdict")
    except ValueError:
        verdict = None

    if not verdict:
        return _runtime_status(
            component="inference_contract",
            status="degraded",
            message="Classifier answered without a verdict.",
            detail="HTTP 200 but the response carries no verdict field.",
            checked_url=inference_url,
            latency_ms=latency,
        )

    return _runtime_status(
        component="inference_contract",
        status="ok",
        message="Authenticated classification returned a verdict.",
        detail=f"verdict={verdict}",
        checked_url=inference_url,
        latency_ms=latency,
    )


async def probe_public_app_runtime(
    client: httpx.AsyncClient,
    public_api_url: str | None,
    probe_base_url: str | None = None,
) -> tuple[list[dict], str | None]:
    if not public_api_url:
        return [
            _runtime_status(
                component="public_app_api",
                status="down",
                message="SICURRE_PUBLIC_API_URL is not configured.",
            )
        ], None

    base_url = public_api_url.rstrip("/")
    scan_url = f"{base_url}/v1/email/scan"
    probe_base = (probe_base_url or base_url).rstrip("/")
    probe_scan_url = f"{probe_base}/v1/email/scan"
    health_url = f"{probe_base}/health"
    results = []

    started = datetime.now(timezone.utc)
    try:
        response = await client.get(health_url)
        results.append(
            _runtime_status(
                component="public_app_health",
                status="ok" if response.status_code == 200 else "down",
                message=f"{response.status_code} response from public Sicurre app API.",
                checked_url=health_url,
                latency_ms=_http_latency_ms(started),
            )
        )
    except Exception as exc:
        results.append(
            _runtime_status(
                component="public_app_health",
                status="down",
                message="Public Sicurre app API health endpoint is unreachable.",
                detail=str(exc)[:220],
                checked_url=health_url,
            )
        )

    started = datetime.now(timezone.utc)
    try:
        response = await client.post(
            probe_scan_url,
            json={
                "subject": "Sicurre preflight probe",
                "sender": "preflight@example.com",
                "text": "Probe without Worker secret.",
                "use_llm": False,
                "use_virustotal": False,
            },
        )
        status_value = "ok" if response.status_code == 401 else "down"
        message = (
            "Scan gateway exists and rejected the probe without Worker secret."
            if response.status_code == 401
            else f"{response.status_code} response from scan gateway; expected 401 without Worker secret."
        )
        results.append(
            _runtime_status(
                component="email_scan_gateway",
                status=status_value,
                message=message,
                checked_url=probe_scan_url,
                latency_ms=_http_latency_ms(started),
            )
        )
    except Exception as exc:
        results.append(
            _runtime_status(
                component="email_scan_gateway",
                status="down",
                message="Worker scan gateway is unreachable.",
                detail=str(exc)[:220],
                checked_url=probe_scan_url,
            )
        )

    return results, scan_url


async def probe_cloudflare_runtime(
    client: httpx.AsyncClient,
    *,
    expected_scan_url: str | None,
) -> list[dict]:
    rows = await quiet_rows(
        """
        SELECT zone_name, zone_id, account_id, worker_name, rule_id, api_token,
               destination_email, status
        FROM cloudflare_integration
        WHERE status IN ('active', 'pending_verification', 'provisioning')
        ORDER BY updated_at DESC
        LIMIT 1
        """
    )
    if not rows:
        return [
            _runtime_status(
                component="cloudflare_worker",
                status="unknown",
                message="No active Cloudflare integration is configured.",
            )
        ]

    row = rows[0]
    encrypted_api_token = row.get("api_token")
    account_id = row.get("account_id")
    worker_name = row.get("worker_name")
    zone_id = row.get("zone_id")
    rule_id = row.get("rule_id")
    results: list[dict] = []

    if not encrypted_api_token or not account_id or not worker_name:
        return [
            _runtime_status(
                component="cloudflare_worker",
                status="down",
                message="Cloudflare integration is missing token, account id, or Worker name.",
                detail=f"zone={row.get('zone_name')} status={row.get('status')}",
            )
        ]

    settings = get_settings()
    try:
        api_token = decrypt_secret(
            encrypted_api_token,
            configured_key=settings.secret_encryption_key,
            environment=settings.environment,
        )
    except ValueError:
        logger.exception("Cloudflare token decryption failed")
        return [
            _runtime_status(
                component="cloudflare_worker",
                status="down",
                message="Cloudflare credential cannot be decrypted.",
            )
        ]
    headers = {"Authorization": f"Bearer {api_token}"}

    settings_url = f"{CF_BASE}/accounts/{account_id}/workers/scripts/{worker_name}/settings"
    try:
        response = await client.get(settings_url, headers=headers)
        payload = response.json()
        bindings = (
            payload.get("result", {}).get("bindings", []) if response.status_code == 200 else []
        )
        scan_binding = next(
            (binding for binding in bindings if binding.get("name") == "SICURRE_SCAN_URL"), {}
        )
        worker_scan_url = scan_binding.get("text")
        matches_expected = bool(expected_scan_url and worker_scan_url == expected_scan_url)
        results.append(
            _runtime_status(
                component="cloudflare_worker_binding",
                status="ok" if matches_expected else "down",
                message=(
                    "Cloudflare Worker points to the configured public scan gateway."
                    if matches_expected
                    else "Cloudflare Worker scan URL does not match the configured public app API."
                ),
                detail=f"worker_scan_url={worker_scan_url or 'missing'}",
                checked_url=worker_scan_url,
            )
        )
    except Exception as exc:
        results.append(
            _runtime_status(
                component="cloudflare_worker_binding",
                status="down",
                message="Could not read Cloudflare Worker bindings.",
                detail=str(exc)[:220],
                checked_url=settings_url,
            )
        )

    if zone_id and rule_id:
        rules_url = f"{CF_BASE}/zones/{zone_id}/email/routing/rules"
        try:
            response = await client.get(rules_url, headers=headers)
            payload = response.json()
            rules = payload.get("result", []) if response.status_code == 200 else []
            rule = next((item for item in rules if item.get("id") == rule_id), None)
            results.append(
                _runtime_status(
                    component="cloudflare_routing_rule",
                    status="ok" if rule and rule.get("enabled") else "down",
                    message=(
                        "Cloudflare routing rule is enabled."
                        if rule and rule.get("enabled")
                        else "Cloudflare routing rule is missing or disabled."
                    ),
                    detail=f"rule_id={rule_id}",
                )
            )
        except Exception as exc:
            results.append(
                _runtime_status(
                    component="cloudflare_routing_rule",
                    status="degraded",
                    message="Could not verify Cloudflare routing rule.",
                    detail=str(exc)[:220],
                    checked_url=rules_url,
                )
            )

    if account_id:
        sending_url = f"{CF_BASE}/accounts/{account_id}/email/routing/addresses"
        try:
            response = await client.get(sending_url, headers=headers)
            payload = response.json()
            addresses = payload.get("result", []) if response.status_code == 200 else []
            destination = str(row.get("destination_email") or "").lower()
            verified = any(
                str(item.get("email") or "").lower() == destination and item.get("verified")
                for item in addresses
            )
            if response.status_code in {401, 403}:
                sending_status = "down"
                sending_message = (
                    "Cloudflare denied access to Email Routing destinations. Confirm "
                    "account-scoped Email Routing Addresses: Read permission."
                )
            elif response.status_code != 200:
                sending_status = "degraded"
                sending_message = "Cloudflare delivery readiness could not be verified."
            elif not verified:
                sending_status = "degraded"
                sending_message = (
                    "The connected Email Routing destination is not verified for releases."
                )
            else:
                sending_status = "ok"
                sending_message = "Verified Email Routing delivery is ready for releases."
            results.append(
                _runtime_status(
                    component="cloudflare_email_sending",
                    status=sending_status,
                    message=sending_message,
                    checked_url=sending_url,
                )
            )
        except Exception as exc:
            results.append(
                _runtime_status(
                    component="cloudflare_email_sending",
                    status="degraded",
                    message="Could not verify Cloudflare Email Sending readiness.",
                    detail=str(exc)[:220],
                    checked_url=sending_url,
                )
            )

    return results


def quarantine_storage_status() -> dict:
    settings = get_settings()
    backend = settings.quarantine_storage_backend.strip().lower()
    if backend == "local":
        production = settings.environment.lower() in {"production", "prod"}
        return _runtime_status(
            component="quarantine_storage",
            status="down" if production else "ok",
            message=(
                "Production quarantine custody must use a private R2 bucket."
                if production
                else "Local quarantine custody is configured for development."
            ),
        )
    try:
        build_quarantine_store(settings)
    except RuntimeError as exc:
        return _runtime_status(
            component="quarantine_storage",
            status="down",
            message="Private quarantine R2 custody is not fully configured.",
            detail=str(exc),
        )
    return _runtime_status(
        component="quarantine_storage",
        status="ok",
        message="Private quarantine R2 custody is configured.",
        detail=f"bucket={settings.quarantine_r2_bucket_name}",
    )
