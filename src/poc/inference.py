"""Local model inference client and explicit POC execution modes."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit

import httpx

from poc.config import PocSettings


class InferenceMode(StrEnum):
    """Inference modes available in the certification POC."""

    LIVE = "live"
    SIMULATION = "simulation"


class FaultScenario(StrEnum):
    """Bounded local API failures available to the resilience demonstration."""

    SERVICE_UNAVAILABLE = "service_unavailable"
    INVALID_BEARER = "invalid_bearer"
    INVALID_CONTRACT = "invalid_contract"


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
    request_method: str = "POST"
    request_path: str = "/v1/classify"
    request_body: dict[str, Any] | None = None
    response_status: int | None = None
    response_body: Any = None
    validation: str = "not_evaluated"
    validation_detail: str = ""
    application_outcome: str = "request_rejected"


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
        except (PocInferenceContractError, ValueError, TypeError) as exc:
            raise PocInferenceContractError(
                "La réponse du modèle local ne respecte pas le contrat attendu."
            ) from exc
        result["source"] = InferenceMode.LIVE.value
        return result

    def run_fault_probe(self, scenario: FaultScenario) -> FaultProbeResult:
        """Observe the fault currently injected into the local POC gateway."""
        payload = self._probe_payload()
        try:
            response = httpx.post(
                self.settings.inference_api_url,
                json=payload,
                headers=self._headers(),
                timeout=5.0,
            )
        except httpx.HTTPError as error:
            return FaultProbeResult(
                scenario=scenario,
                expected=self._fault_expectation(scenario),
                observed=type(error).__name__,
                passed=False,
                request_path=self._classify_path(),
                request_body=payload,
                validation_detail=type(error).__name__,
            )
        response_body = self._safe_response_body(response)
        if scenario == FaultScenario.INVALID_CONTRACT:
            try:
                normalize_inference_result(response.json())
            except (PocInferenceContractError, ValueError, TypeError):
                return FaultProbeResult(
                    scenario,
                    "contract_rejected",
                    "contract_rejected",
                    True,
                    request_path=self._classify_path(),
                    request_body=payload,
                    response_status=response.status_code,
                    response_body=response_body,
                    validation="rejected",
                    validation_detail="required_fields_missing_or_invalid",
                    application_outcome="response_rejected_not_persisted",
                )
            return FaultProbeResult(
                scenario,
                "contract_rejected",
                "contract_accepted",
                False,
                request_path=self._classify_path(),
                request_body=payload,
                response_status=response.status_code,
                response_body=response_body,
                validation="accepted",
                application_outcome="unexpected_acceptance",
            )
        expected_status = 503 if scenario == FaultScenario.SERVICE_UNAVAILABLE else 401
        return FaultProbeResult(
            scenario=scenario,
            expected=str(expected_status),
            observed=str(response.status_code),
            passed=response.status_code == expected_status,
            request_path=self._classify_path(),
            request_body=payload,
            response_status=response.status_code,
            response_body=response_body,
            validation="not_evaluated",
            validation_detail="http_rejected_before_validation",
            application_outcome=(
                "service_unavailable" if expected_status == 503 else "authentication_rejected"
            ),
        )

    def run_recovery_probe(self) -> FaultProbeResult:
        """Verify restored inference with one synthetic contract-valid request."""
        payload = self._probe_payload()
        scenario = FaultScenario.INVALID_CONTRACT
        response: httpx.Response | None = None
        response_body: Any = None
        try:
            response = httpx.post(
                self.settings.inference_api_url,
                json=payload,
                headers=self._headers(),
                timeout=self.timeout_seconds,
            )
            response_body = self._safe_response_body(response)
            response.raise_for_status()
            normalize_inference_result(response.json())
        except (httpx.HTTPError, PocInferenceContractError, ValueError, TypeError) as error:
            return FaultProbeResult(
                scenario,
                "contract_accepted",
                type(error).__name__,
                False,
                request_path=self._classify_path(),
                request_body=payload,
                response_status=response.status_code if response is not None else None,
                response_body=response_body,
                validation="rejected",
                validation_detail=f"recovery_error:{type(error).__name__}",
                application_outcome="recovery_failed",
            )
        return FaultProbeResult(
            scenario,
            "contract_accepted",
            "contract_accepted",
            True,
            request_path=self._classify_path(),
            request_body=payload,
            response_status=response.status_code,
            response_body=response_body,
            validation="accepted",
            validation_detail="required_fields_accepted",
            application_outcome="recovery_verified_not_persisted",
        )

    @staticmethod
    def _fault_expectation(scenario: FaultScenario) -> str:
        if scenario == FaultScenario.INVALID_CONTRACT:
            return "contract_rejected"
        return "503" if scenario is FaultScenario.SERVICE_UNAVAILABLE else "401"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.inference_api_key}"}

    @staticmethod
    def _probe_payload() -> dict[str, Any]:
        return {
            "subject": "Contrôle de résilience Sicurre",
            "sender": "probe@sicurre.test",
            "text": "Message local synthétique sans donnée utilisateur.",
            "use_llm": False,
            "use_virustotal": False,
        }

    def _classify_path(self) -> str:
        return urlsplit(self.settings.inference_api_url).path

    @staticmethod
    def _safe_response_body(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return response.text[:1000]
