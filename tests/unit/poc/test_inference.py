"""Tests for explicit POC inference modes and API failures."""

import httpx
import pytest
import respx

from poc.config import PocSettings
from poc.inference import (
    ClassificationRequest,
    InferenceMode,
    PocInferenceClient,
    PocInferenceContractError,
    PocInferenceUnavailable,
    normalize_inference_result,
)


@pytest.fixture
def configured_settings() -> PocSettings:
    return PocSettings(
        _env_file=None,
        database_url="sqlite:////tmp/poc-auth.db",
        data_platform_database_url="sqlite:////tmp/poc-data.db",
        inference_api_url="http://model.test/v1/classify",
        inference_api_key="internal-test-key",
        admin_password="admin-secret",
        viewer_password="viewer-secret",
    )


@pytest.fixture
def classification_request() -> ClassificationRequest:
    return ClassificationRequest(
        subject="Compte suspendu urgent",
        sender="security@example.test",
        text="Confirmez votre mot de passe.",
    )


def test_simulation_is_deterministic_and_explicit(
    configured_settings: PocSettings, classification_request: ClassificationRequest
) -> None:
    client = PocInferenceClient(configured_settings)
    first = client.classify(classification_request, mode=InferenceMode.SIMULATION)
    second = client.classify(classification_request, mode=InferenceMode.SIMULATION)
    assert first["source"] == "simulation"
    assert first["label_verdict"] == "phishing"
    assert first["composite_score"] == second["composite_score"]


def test_incident_mode_never_calls_the_network(
    configured_settings: PocSettings, classification_request: ClassificationRequest
) -> None:
    with respx.mock(assert_all_called=False) as router:
        route = router.post(configured_settings.inference_api_url)
        with pytest.raises(PocInferenceUnavailable, match="Incident contrôlé"):
            PocInferenceClient(configured_settings).classify(
                classification_request, mode=InferenceMode.INCIDENT
            )
        assert not route.called


@respx.mock
def test_live_mode_sends_bearer_key_and_normalizes_response(
    configured_settings: PocSettings, classification_request: ClassificationRequest
) -> None:
    route = respx.post(configured_settings.inference_api_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "verdict": "phishing",
                "label_verdict": "phishing",
                "is_phishing": True,
                "composite_score": 0.94,
            },
        )
    )
    result = PocInferenceClient(configured_settings).classify(classification_request)
    assert route.calls[0].request.headers["Authorization"] == "Bearer internal-test-key"
    assert result["source"] == "live"
    assert result["label_verdict"] == "phishing"


@respx.mock
def test_live_authentication_failure_is_contextual(
    configured_settings: PocSettings, classification_request: ClassificationRequest
) -> None:
    respx.post(configured_settings.inference_api_url).mock(return_value=httpx.Response(401))
    with pytest.raises(PocInferenceUnavailable, match="HTTP 401"):
        PocInferenceClient(configured_settings).classify(classification_request)


def test_invalid_model_contract_is_rejected() -> None:
    with pytest.raises(PocInferenceContractError, match="invalid verdict"):
        normalize_inference_result({"verdict": "unknown"})


def test_invalid_class_label_is_rejected() -> None:
    with pytest.raises(PocInferenceContractError, match="invalid class label"):
        normalize_inference_result({"verdict": "safe", "label_verdict": "other"})


def test_missing_key_reports_unavailable_health(
    configured_settings: PocSettings,
) -> None:
    settings_without_key = configured_settings.model_copy(update={"inference_api_key": ""})
    assert PocInferenceClient(settings_without_key).health() == (
        False,
        "Clé d'inférence POC absente",
    )


@respx.mock
def test_health_reports_success_and_http_failure(
    configured_settings: PocSettings,
) -> None:
    health_url = "http://model.test/health"
    health_route = respx.get(health_url).mock(return_value=httpx.Response(200))
    auth_route = respx.post(configured_settings.inference_api_url).mock(
        return_value=httpx.Response(422)
    )
    client = PocInferenceClient(configured_settings)
    assert client.health() == (True, "Service local disponible et authentifié")
    assert auth_route.calls[0].request.content == b"{}"
    health_route.mock(return_value=httpx.Response(503))
    assert client.health() == (False, "HTTP 503")


@respx.mock
def test_health_reports_rejected_bearer_key(
    configured_settings: PocSettings,
) -> None:
    respx.get("http://model.test/health").mock(return_value=httpx.Response(200))
    respx.post(configured_settings.inference_api_url).mock(return_value=httpx.Response(401))

    assert PocInferenceClient(configured_settings).health() == (
        False,
        "Clé d'inférence locale refusée",
    )


@respx.mock
def test_health_reports_network_failure(configured_settings: PocSettings) -> None:
    respx.get("http://model.test/health").mock(side_effect=httpx.ConnectError("offline"))
    available, detail = PocInferenceClient(configured_settings).health()
    assert available is False
    assert "ConnectError" in detail


@respx.mock
def test_live_network_failure_is_contextual(
    configured_settings: PocSettings, classification_request: ClassificationRequest
) -> None:
    respx.post(configured_settings.inference_api_url).mock(
        side_effect=httpx.ConnectError("offline")
    )
    with pytest.raises(PocInferenceUnavailable, match="ne répond pas"):
        PocInferenceClient(configured_settings).classify(classification_request)


@respx.mock
def test_live_invalid_json_is_a_contract_error(
    configured_settings: PocSettings, classification_request: ClassificationRequest
) -> None:
    respx.post(configured_settings.inference_api_url).mock(
        return_value=httpx.Response(200, text="not-json")
    )
    with pytest.raises(PocInferenceContractError, match="réponse du modèle"):
        PocInferenceClient(configured_settings).classify(classification_request)
