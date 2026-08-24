"""Tests for explicit POC inference modes and API failures."""

import httpx
import pytest
import respx

from poc.config import PocSettings
from poc.inference import (
    ClassificationRequest,
    FaultScenario,
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
        inference_api_url="http://127.0.0.1:8765/v1/classify",
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


@respx.mock
def test_fault_probes_exercise_real_request_boundaries(
    configured_settings: PocSettings,
) -> None:
    classify_route = respx.post(configured_settings.inference_api_url)
    classify_route.mock(return_value=httpx.Response(401))
    client = PocInferenceClient(configured_settings)

    auth_result = client.run_fault_probe(FaultScenario.INVALID_BEARER)
    assert auth_result.passed
    assert auth_result.observed == "401"
    assert classify_route.calls[-1].request.headers["Authorization"].endswith("invalid-probe")

    classify_route.mock(return_value=httpx.Response(422))
    payload_result = client.run_fault_probe(FaultScenario.INVALID_PAYLOAD)
    assert payload_result.passed
    assert payload_result.observed == "422"


@respx.mock
def test_unreachable_fault_probe_records_connection_failure(
    configured_settings: PocSettings,
) -> None:
    respx.post("http://127.0.0.1:1/v1/classify").mock(side_effect=httpx.ConnectError("offline"))
    result = PocInferenceClient(configured_settings).run_fault_probe(
        FaultScenario.UNREACHABLE_ENDPOINT
    )
    assert result.passed
    assert result.observed == "ConnectError"


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
        "inference_health_missing_key",
    )


@respx.mock
def test_health_reports_success_and_http_failure(
    configured_settings: PocSettings,
) -> None:
    health_url = "http://127.0.0.1:8765/health"
    health_route = respx.get(health_url).mock(return_value=httpx.Response(200))
    auth_route = respx.post(configured_settings.inference_api_url).mock(
        return_value=httpx.Response(422)
    )
    client = PocInferenceClient(configured_settings)
    assert client.health() == (True, "inference_health_ready")
    assert auth_route.calls[0].request.content == b"{}"
    health_route.mock(return_value=httpx.Response(503))
    assert client.health() == (False, "inference_health_unavailable")


@respx.mock
def test_health_reports_rejected_bearer_key(
    configured_settings: PocSettings,
) -> None:
    respx.get("http://127.0.0.1:8765/health").mock(return_value=httpx.Response(200))
    respx.post(configured_settings.inference_api_url).mock(return_value=httpx.Response(401))

    assert PocInferenceClient(configured_settings).health() == (
        False,
        "inference_health_rejected",
    )


@respx.mock
def test_health_reports_unexpected_contract_status(
    configured_settings: PocSettings,
) -> None:
    respx.get("http://127.0.0.1:8765/health").mock(return_value=httpx.Response(200))
    respx.post(configured_settings.inference_api_url).mock(return_value=httpx.Response(200))

    assert PocInferenceClient(configured_settings).health() == (
        False,
        "inference_health_unexpected",
    )


@respx.mock
def test_health_reports_network_failure(configured_settings: PocSettings) -> None:
    respx.get("http://127.0.0.1:8765/health").mock(side_effect=httpx.ConnectError("offline"))
    available, detail = PocInferenceClient(configured_settings).health()
    assert available is False
    assert detail == "inference_health_unavailable"


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
