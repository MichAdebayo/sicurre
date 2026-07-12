from __future__ import annotations

from data_platform.services.certfr.stage_two import CertFRStageTwoService


def test_certfr_stage_two_marks_threat_intel_and_extracts_ioc_counts() -> None:
    result = CertFRStageTwoService.review(
        (
            "CERTFR-2025-CTI-003 Panorama de la cybermenace. "
            "L'infrastructure associe le domaine evil-phishing.fr et l'email attacker@malware-domain.net."
        ),
        {"title": "Panorama de la cybermenace 2025"},
    )

    assert result.route_outcome == "specialized_processing"
    assert result.route_subtype == "threat_intel"
    assert result.derived_payload is not None
    assert result.derived_payload["ioc_counts"]["domains"] >= 1
    assert result.derived_payload["ioc_counts"]["emails"] == 1
    assert "evil-phishing.fr" in result.derived_payload["iocs"]["domains"]


def test_certfr_stage_two_marks_synthetic_lure_candidate() -> None:
    result = CertFRStageTwoService.review(
        (
            "Objet: Vérification urgente Bonjour, veuillez confirmer votre compte sans délai. "
            "Cliquez sur le lien sécurisé pour éviter la suspension de votre accès."
        ),
        {"title": "Exemple de leurre"},
    )

    assert result.route_outcome == "specialized_processing"
    assert result.route_subtype == "synthetic_lure_candidate"
    assert result.derived_payload is not None
    assert result.derived_payload["is_synthetic"] is True
    assert result.derived_payload["iocs"] == {}
