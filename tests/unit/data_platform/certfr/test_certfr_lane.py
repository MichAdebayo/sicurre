"""The CERT-FR chain must actually run, not merely be runnable.

Five CERT-FR services existed, each unit-tested, and only the router had a
caller. The other four were never invoked, so 88 ANSSI records routed to a
destination nothing reached. Those unit tests could not catch it: they
instantiate a service and assert it behaves, which says nothing about whether
the sequence is ever executed.

These tests exercise the sequence.
"""

from __future__ import annotations

from data_platform.services.certfr.lane import (
    CONSUMED_SUBTYPES,
    build_certfr_generation_bundle,
    build_signal_bank,
)
from data_platform.services.certfr.stage_two import CertFRStageTwoService

# A CTI report needs its report markers in the first 800 characters to route as
# threat intelligence; without them stage_two picks a different subtype and the
# summary ignores the record entirely.
CTI_REPORT = (
    "ANSSI - CERT-FR  TLP:CLEAR  Table des matieres. "
    "Panorama de la cybermenace. Le CERT-FR a observe une campagne de hameconnage "
    "bancaire ciblant les clients francais par courriel. Les messages usurpent "
    "l identite d une banque et demandent la confirmation des coordonnees "
    "bancaires et du RIB. Domaines malveillants: bnp-verif.top. "
    "Adresses: alerte@bnp-verif.top. IP: 192.0.2.10"
)


def _records() -> list[dict]:
    return [{"raw_record_id": "r1", "raw_content": {"text": CTI_REPORT}}]


def test_cti_reports_reach_the_threat_intel_rule() -> None:
    """build_summary reads only threat_intel and procedural_notification."""
    bank = build_signal_bank(_records())

    rules = {r["key"]: r["current_count"] for r in bank["sources"][0]["rules"]}
    assert rules["threat_intel"] >= 1


def test_the_chain_produces_french_phishing_drafts() -> None:
    bundle = build_certfr_generation_bundle(_records(), run_timestamp="2026-09-01T00:00:00Z")

    samples = bundle.get("samples", [])
    assert samples, "the CERT-FR chain produced no drafts"
    for sample in samples:
        assert sample["target_label"] == "phishing"
        assert sample["language"] == "fr"
        assert sample["source_name"] == "cert-fr-cti"
        assert sample["normalized_text"].startswith("Objet : ")
        assert sample["text_sha256"]


def test_drafts_use_the_builders_own_text_not_a_second_format() -> None:
    """Rebuilding "Objet : …" here would be a second definition free to drift."""
    bundle = build_certfr_generation_bundle(_records())

    for sample in bundle["samples"]:
        assert "\n\n" in sample["normalized_text"]


def test_an_unlisted_router_subtype_is_surfaced_not_discarded() -> None:
    """A subtype added to the router without a consumer must stay visible.

    This is the exact failure being fixed: routing to a destination nothing
    consumes, silently. Discarding unknown subtypes here would reproduce it one
    level down.
    """
    embedded_lure = (
        "Bonjour, votre compte sera suspendu. Veuillez confirmer votre RIB "
        "via le portail securise. Objet: verification de votre compte."
    )
    bank = build_signal_bank(
        [{"raw_record_id": "x", "raw_content": {"text": embedded_lure}}]
    )

    keys = {rule["key"] for rule in bank["sources"][0]["rules"]}
    routed = CertFRStageTwoService.review(embedded_lure, {}).route_subtype

    assert routed in keys, "a routed subtype vanished from the signal bank"


def test_consumed_subtypes_are_declared_explicitly() -> None:
    """The declared list is what makes an unhandled subtype noticeable."""
    assert "threat_intel" in CONSUMED_SUBTYPES
    assert "procedural_notification" in CONSUMED_SUBTYPES


def test_empty_input_does_not_raise() -> None:
    bundle = build_certfr_generation_bundle([])

    assert bundle.get("samples") == []
