from __future__ import annotations

from data_platform.services.certfr.signal_summary import CertFRSignalSummaryService


def test_certfr_signal_summary_aggregates_themes_and_iocs() -> None:
    summary = CertFRSignalSummaryService.build_summary(
        {
            "sources": [
                {
                    "source_name": "cert-fr-cti",
                    "rules": [
                        {
                            "key": "threat_intel",
                            "current_count": 2,
                            "sampled_records": [
                                {
                                    "raw_record_id": "a",
                                    "normalized_preview": "Objet: Rançongiciel Maze et campagne de phishing par courriel",
                                    "derived_payload": {
                                        "phishing_relevance": True,
                                        "ioc_counts": {
                                            "domains": 1,
                                            "emails": 0,
                                            "ips": 2,
                                            "hashes": 0,
                                        },
                                    },
                                },
                                {
                                    "raw_record_id": "b",
                                    "normalized_preview": "Le groupe Dridex utilise le courriel comme vecteur principal",
                                    "derived_payload": {
                                        "phishing_relevance": False,
                                        "ioc_counts": {
                                            "domains": 0,
                                            "emails": 1,
                                            "ips": 0,
                                            "hashes": 0,
                                        },
                                    },
                                },
                            ],
                        },
                        {
                            "key": "procedural_notification",
                            "sampled_records": [
                                {
                                    "raw_record_id": "c",
                                    "normalized_preview": "courriel d'alerte Apple",
                                }
                            ],
                        },
                    ],
                }
            ]
        }
    )

    assert summary["threat_intel_total_count"] == 2
    assert summary["phishing_relevant_sampled_count"] == 1
    assert summary["ioc_totals"]["domains"] == 1
    assert summary["ioc_totals"]["ips"] == 2
    assert summary["family_counts"]["maze"] == 1
    assert summary["family_counts"]["dridex"] == 1
    assert summary["theme_counts"]["ransomware"] == 1
    assert summary["channel_counts"]["email"] >= 1


def test_certfr_signal_summary_render_markdown() -> None:
    markdown = CertFRSignalSummaryService.render_markdown(
        {
            "generated_at": "2026-04-07T00:00:00+00:00",
            "threat_intel_total_count": 2,
            "sampled_threat_intel_count": 2,
            "sampled_procedural_count": 1,
            "phishing_relevant_sampled_count": 1,
            "ioc_totals": {"domains": 1},
            "family_counts": {"maze": 1},
            "theme_counts": {"ransomware": 1},
            "channel_counts": {"email": 1},
        }
    )

    assert "# CERT-FR Signal Summary" in markdown
    assert "Threat-intel total count" in markdown
