"""Tests for the reversible loopback-only POC fault gateway."""

from __future__ import annotations

from collections.abc import Iterator
from enum import StrEnum

import httpx
import pytest

from poc.fault_gateway import PocFaultGateway, gateway_settings_url
from poc.inference import FaultScenario


@pytest.fixture
def gateway() -> Iterator[PocFaultGateway]:
    instance = PocFaultGateway("http://127.0.0.1:8765/v1/classify").start()
    try:
        yield instance
    finally:
        instance.close()


def test_gateway_proxies_nominal_requests(
    gateway: PocFaultGateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed: dict[str, object] = {}

    def fake_request(method: str, url: str, **kwargs: object) -> httpx.Response:
        observed.update(method=method, url=url, kwargs=kwargs)
        return httpx.Response(422, json={"detail": "validation"})

    monkeypatch.setattr(httpx, "request", fake_request)
    response = httpx.post(
        gateway.classify_url,
        json={},
        headers={"Authorization": "Bearer expected"},
    )

    assert response.status_code == 422
    assert observed["url"] == "http://127.0.0.1:8765/v1/classify"
    forwarded_headers = observed["kwargs"]["headers"]  # type: ignore[index]
    assert forwarded_headers["Authorization"] == "Bearer expected"
    assert gateway_settings_url(gateway) == gateway.classify_url


def test_gateway_injects_each_fault_and_restores(
    gateway: PocFaultGateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_request(method: str, url: str, **kwargs: object) -> httpx.Response:
        headers = kwargs.get("headers", {})
        authorization = str(headers.get("Authorization", ""))  # type: ignore[union-attr]
        return httpx.Response(401 if authorization.endswith("invalid-key") else 422)

    monkeypatch.setattr(httpx, "request", fake_request)

    gateway.inject(FaultScenario.SERVICE_UNAVAILABLE)
    health_url = gateway.classify_url.removesuffix("/v1/classify") + "/health"
    assert httpx.get(health_url).status_code == 503

    gateway.inject(FaultScenario.INVALID_BEARER)
    assert httpx.post(gateway.classify_url, json={}).status_code == 401

    gateway.inject(FaultScenario.INVALID_CONTRACT)
    assert httpx.post(gateway.classify_url, json={}).json() == {"unexpected": True}

    gateway.restore()
    assert gateway.active_scenario is None
    assert httpx.post(gateway.classify_url, json={}).status_code == 422


def test_gateway_fault_persists_and_unknown_routes_are_rejected(
    gateway: PocFaultGateway, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        httpx,
        "request",
        lambda *args, **kwargs: httpx.Response(200, json={"status": "ok"}),
    )
    gateway.inject(FaultScenario.SERVICE_UNAVAILABLE)

    assert gateway.active_scenario is FaultScenario.SERVICE_UNAVAILABLE
    health_url = gateway.classify_url.removesuffix("/v1/classify") + "/health"
    assert httpx.get(health_url).status_code == 503
    assert httpx.get(health_url.removesuffix("/health") + "/missing").status_code == 404


def test_gateway_matches_fault_value_after_module_reload(
    gateway: PocFaultGateway,
) -> None:
    """A cached gateway must accept an equivalent enum from reloaded app code."""

    class ReloadedFaultScenario(StrEnum):
        SERVICE_UNAVAILABLE = "service_unavailable"

    gateway.inject(ReloadedFaultScenario.SERVICE_UNAVAILABLE)  # type: ignore[arg-type]

    health_url = gateway.classify_url.removesuffix("/v1/classify") + "/health"
    assert httpx.get(health_url).status_code == 503
    assert httpx.post(gateway.classify_url, json={}).status_code == 503


def test_closed_gateway_has_no_runtime_url(gateway: PocFaultGateway) -> None:
    gateway.close()
    gateway.close()
    with pytest.raises(RuntimeError, match="not started"):
        _ = gateway.classify_url
