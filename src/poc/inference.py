"""Local model inference client and explicit POC execution modes."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx

from poc.config import PocSettings


class InferenceMode(StrEnum):
    """Inference modes available in the certification POC."""

    LIVE = "live"
    SIMULATION = "simulation"


class FaultScenario(StrEnum):
    """Bounded local API failures available to the resilience demonstration."""

    INVALID_BEARER = "invalid_bearer"
    INVALID_PAYLOAD = "invalid_payload"
    UNREACHABLE_ENDPOINT = "unreachable_endpoint"


class PocInferenceError(RuntimeError):
    """Base error raised when a POC classification cannot complete."""


class PocInferenceUnavailable(PocInferenceError):
    """Raised when the local model API cannot be reached or authenticated."""


class PocInferenceContractError(PocInferenceError):
    """Raised when the local model API violates its documented response contract."""


@dataclass(frozen=True)
class FaultProbeResult:
    """Observed evidence from one non-destructive local fault probe."""

    scenario: FaultScenario
    expected: str
    observed: str
    passed: bool


@dataclass(frozen=True)
class ClassificationRequest:
    """Input accepted by the local classifier demonstration."""

    subject: str
    sender: str
    text: str
    use_llm: bool = True
    use_virustotal: bool = True


def normalize_inference_result(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize the model response into the POC presentation contract."""
    verdict = str(raw.get("verdict") or "").lower()
    if verdict not in {"safe", "phishing"}:
        raise PocInferenceContractError("Inference response has an invalid verdict.")
    is_phishing = bool(raw.get("is_phishing", verdict == "phishing"))
    label_verdict = str(
        raw.get("label_verdict")
        or (raw.get("stage_labels") or {}).get("onnx")
        or ("phishing" if is_phishing else "legitimate")
    ).lower()
    if label_verdict not in {"legitimate", "spam", "phishing"}:
        raise PocInferenceContractError("Inference response has an invalid class label.")

    return {
        "safety_verdict": "phishing" if is_phishing else "safe",
        "label_verdict": label_verdict,
        "is_phishing": is_phishing,
        "composite_score": float(raw.get("composite_score") or 0.0),
        "llm_provider": str(raw.get("llm_provider") or "n/a"),
        "explanation": str(raw.get("explanation") or ""),
        "stage_scores": raw.get("stage_scores") or {},
        "stage_labels": raw.get("stage_labels") or {},
        "label_distribution": raw.get("label_distribution") or {},
        "stage_breakdown": raw.get("stage_breakdown") or {},
        "raw": raw,
    }


def simulated_result(request: ClassificationRequest) -> dict[str, Any]:
    """Return a deterministic and explicitly labelled demonstration result."""
    full = f"{request.subject} {request.sender} {request.text}".lower()
    phishing_hits = sum(
        term in full
        for term in ("urgent", "mot de passe", "rib", "suspendu", "verifier", "confirmez")
    )
    spam_hits = sum(
        term in full for term in ("promo", "offre", "gratuit", "bonus", "remise", "leads")
    )
    if phishing_hits >= 2:
        label, score = "phishing", 0.78
    elif spam_hits >= 2:
        label, score = "spam", 0.28
    else:
        label, score = "legitimate", 0.08
    result = normalize_inference_result(
        {
            "verdict": "phishing" if label == "phishing" else "safe",
            "label_verdict": label,
            "is_phishing": label == "phishing",
            "composite_score": score,
            "stage_scores": {"simulation": score},
            "stage_labels": {"simulation": label},
            "explanation": "Résultat déterministe du mode simulation, sans appel au modèle.",
            "llm_provider": "simulation",
        }
    )
    result["source"] = InferenceMode.SIMULATION.value
    return result


class PocInferenceClient:
    """Call the local authenticated classifier without silent degradation."""

    def __init__(self, settings: PocSettings, *, timeout_seconds: float = 35.0) -> None:
        self.settings = settings
        self.timeout_seconds = timeout_seconds

    def health(self) -> tuple[bool, str]:
        """Return local model API and bearer-contract availability."""
        if not self.settings.inference_api_key:
            return False, "inference_health_missing_key"
        health_url = self.settings.inference_api_url.removesuffix("/v1/classify") + "/health"
        try:
            health_response = httpx.get(
                health_url,
                timeout=5.0,
            )
            if not health_response.is_success:
                return False, "inference_health_unavailable"
            auth_response = httpx.post(
                self.settings.inference_api_url,
                json={},
                headers=self._headers(),
                timeout=5.0,
            )
        except httpx.HTTPError:
            return False, "inference_health_unavailable"
        if auth_response.status_code == 401:
            return False, "inference_health_rejected"
        if auth_response.status_code == 422:
            return True, "inference_health_ready"
        return False, "inference_health_unexpected"

    def classify(
        self,
        request: ClassificationRequest,
        *,
        mode: InferenceMode = InferenceMode.LIVE,
    ) -> dict[str, Any]:
        """Classify one message in a deliberately selected POC mode."""
        started = time.perf_counter()
        if mode is InferenceMode.SIMULATION:
            result = simulated_result(request)
        else:
            result = self._classify_live(request)
        result["params"] = {
            "use_llm": request.use_llm,
            "use_virustotal": request.use_virustotal,
        }
        result["latency_ms"] = round((time.perf_counter() - started) * 1000.0, 2)
        return result

    def _classify_live(self, request: ClassificationRequest) -> dict[str, Any]:
        if not self.settings.inference_api_key:
            raise PocInferenceUnavailable("SICURRE_POC_INFERENCE_API_KEY est absente.")
        try:
            response = httpx.post(
                self.settings.inference_api_url,
                json={
                    "subject": request.subject,
                    "sender": request.sender,
                    "text": request.text,
                    "use_llm": request.use_llm,
                    "use_virustotal": request.use_virustotal,
                },
                headers=self._headers(),
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise PocInferenceUnavailable(
                f"Le service local a refusé la requête (HTTP {exc.response.status_code})."
            ) from exc
        except httpx.HTTPError as exc:
            raise PocInferenceUnavailable("Le service d'inférence local ne répond pas.") from exc
        try:
            result = normalize_inference_result(response.json())
        except (ValueError, TypeError) as exc:
            raise PocInferenceContractError("La réponse du modèle local est invalide.") from exc
        result["source"] = InferenceMode.LIVE.value
        return result

    def run_fault_probe(self, scenario: FaultScenario) -> FaultProbeResult:
        """Exercise one real request failure without stopping the shared service."""
        if scenario is FaultScenario.UNREACHABLE_ENDPOINT:
            try:
                httpx.post("http://127.0.0.1:1/v1/classify", json={}, timeout=0.5)
            except httpx.HTTPError as error:
                return FaultProbeResult(
                    scenario=scenario,
                    expected="connection_error",
                    observed=type(error).__name__,
                    passed=True,
                )
            return FaultProbeResult(scenario, "connection_error", "request_succeeded", False)

        headers = self._headers()
        if scenario is FaultScenario.INVALID_BEARER:
            headers = {"Authorization": "Bearer sicurre-poc-invalid-probe"}
        try:
            response = httpx.post(
                self.settings.inference_api_url,
                json={},
                headers=headers,
                timeout=5.0,
            )
        except httpx.HTTPError as error:
            return FaultProbeResult(
                scenario=scenario,
                expected="401" if scenario is FaultScenario.INVALID_BEARER else "422",
                observed=type(error).__name__,
                passed=False,
            )
        expected_status = 401 if scenario is FaultScenario.INVALID_BEARER else 422
        return FaultProbeResult(
            scenario=scenario,
            expected=str(expected_status),
            observed=str(response.status_code),
            passed=response.status_code == expected_status,
        )

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.inference_api_key}"}
