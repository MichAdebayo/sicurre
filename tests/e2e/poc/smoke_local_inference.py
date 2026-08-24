"""Authenticated end-to-end smoke test for the loopback POC classifier."""

from __future__ import annotations

import sys

from poc.config import get_poc_settings
from poc.inference import ClassificationRequest, PocInferenceClient, PocInferenceError

PROBES = (
    (
        ClassificationRequest(
            subject="Votre carte Vitale expire - renouvellement obligatoire",
            sender="contact@ameli-renouvellement.fr",
            text=(
                "Bonjour, votre carte Vitale arrive à expiration. Sans renouvellement, "
                "vos remboursements seront suspendus. Munissez-vous de votre numéro de "
                "sécurité sociale, d'une pièce d'identité et de votre RIB, puis complétez "
                "votre dossier : https://ameli-renouvellement.fr/carte-vitale-2026"
            ),
            use_llm=False,
            use_virustotal=False,
        ),
        "phishing",
    ),
    (
        ClassificationRequest(
            subject="Offre exceptionnelle",
            sender="offres@catalogue-exemple.test",
            text="Profitez de cette remise promotionnelle réservée à nos abonnés.",
            use_llm=False,
            use_virustotal=False,
        ),
        "spam",
    ),
    (
        ClassificationRequest(
            subject="Compte-rendu de réunion",
            sender="camille@entreprise-exemple.test",
            text="Bonjour, voici le compte-rendu convenu. Merci de confirmer la prochaine date.",
            use_llm=False,
            use_virustotal=False,
        ),
        "legitimate",
    ),
)


def main() -> int:
    """Verify local authentication, readiness, and the three-class contract."""
    settings = get_poc_settings()
    client = PocInferenceClient(settings)
    healthy, status = client.health()
    print(f"POC inference endpoint: {settings.inference_api_url}")
    print(f"Preflight: {status}")
    if not healthy:
        return 1

    failed = False
    for request, expected_label in PROBES:
        try:
            result = client.classify(request)
        except PocInferenceError as exc:
            print(f"FAIL {expected_label}: {exc}", file=sys.stderr)
            failed = True
            continue
        actual_label = str(result["label_verdict"])
        print(
            f"{actual_label}: phishing risk={float(result['composite_score']):.3f}, "
            f"latency={float(result['latency_ms']):.1f} ms"
        )
        if actual_label != expected_label:
            print(
                f"FAIL expected {expected_label}, received {actual_label}",
                file=sys.stderr,
            )
            failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
