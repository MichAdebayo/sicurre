from __future__ import annotations

import asyncio
import os
import sys
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True, slots=True)
class SmokeCheck:
    name: str
    method: str
    path: str
    authenticated: bool = False


CHECKS = (
    SmokeCheck("health", "GET", "/health"),
    SmokeCheck("openapi", "GET", "/openapi.json"),
    SmokeCheck("data sources", "GET", "/v1/data/sources?limit=1", True),
    SmokeCheck("datasets", "GET", "/v1/data/datasets?limit=1", True),
)


def _assert_openapi_paths(payload: dict[str, Any]) -> None:
    paths = payload.get("paths")
    if not isinstance(paths, dict):
        raise AssertionError("OpenAPI payload has no paths object")
    required = {
        "/v1/data/datasets",
        "/v1/data/datasets/{id}/publish",
        "/v1/data/sources",
        "/v1/email/scan",
    }
    missing = sorted(required.difference(paths))
    if missing:
        raise AssertionError(f"OpenAPI is missing expected paths: {missing}")


async def _run_smoke() -> None:
    base_url = os.environ.get("SICURRE_STAGING_API_URL", "http://127.0.0.1:8001")
    token = os.environ.get("SICURRE_STAGING_SMOKE_TOKEN", "dev-token")
    headers = {"Authorization": f"Bearer {token}"}
    timeout = httpx.Timeout(20.0)

    async with httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout) as client:
        openapi_payload: dict[str, Any] | None = None
        for check in CHECKS:
            response = await client.request(
                check.method,
                check.path,
                headers=headers if check.authenticated else None,
            )
            response.raise_for_status()
            if check.name == "openapi":
                openapi_payload = response.json()
            print(f"ok: {check.name} {check.method} {check.path}")

        if openapi_payload is None:
            raise AssertionError("OpenAPI check did not run")
        _assert_openapi_paths(openapi_payload)
        print("ok: expected OpenAPI paths are present")


def main() -> int:
    try:
        asyncio.run(_run_smoke())
    except Exception as exc:
        print(f"staging smoke failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
