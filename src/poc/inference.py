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
    INCIDENT = "incident"


class PocInferenceError(RuntimeError):
    """Base error raised when a POC classification cannot complete."""


class PocInferenceUnavailable(PocInferenceError):
    """Raised when the local model API cannot be reached or authenticated."""


class PocInferenceContractError(PocInferenceError):
    """Raised when the local model API violates its documented response contract."""


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
        "explanation": str(raw.get("explanation") or "Aucune explication fournie."),
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
        """Return local model API availability without exposing credentials."""
        if not self.settings.inference_api_key:
            return False, "Clé d'inférence POC absente"
        health_url = self.settings.inference_api_url.removesuffix("/v1/classify") + "/health"
        try:
            response = httpx.get(
                health_url,
                headers=self._headers(),
                timeout=5.0,
            )
        except httpx.HTTPError as exc:
            return False, f"Service local indisponible: {type(exc).__name__}"
        return (
            response.is_success,
            "Service local disponible" if response.is_success else f"HTTP {response.status_code}",
        )

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
        elif mode is InferenceMode.INCIDENT:
            raise PocInferenceUnavailable(
                "Incident contrôlé: le service d'inférence local est volontairement indisponible."
            )
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

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.settings.inference_api_key}"}
