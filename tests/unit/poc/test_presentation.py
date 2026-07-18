"""Unit tests for testable POC presentation services."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from poc.presentation.datasets import (
    _load_frozen_source_distribution,
    _source_family,
    _source_family_rows,
    _source_label,
)
from poc.presentation.formatting import (
    effective_label,
    effective_verdict,
    format_number,
    hash_token,
    remove_links,
    safe_text,
)
from poc.presentation.home import calculate_home_metrics
from poc.presentation.i18n import PocTranslator
from poc.presentation.pipeline_page import redact_terminal_line
from poc.presentation.remediation import filter_threats, partition_delivered_events
from poc.presentation.result import confidence_bar, result_style
from poc.presentation.theme import initialize_theme, load_theme_css, set_theme


def test_dataset_source_labels_preserve_real_sources_and_shorten_reconstruction() -> None:
    """Recovered provenance remains readable without disguising real source names."""
    translations = {
        "reconstructed_source_native_external": "Recovered external sources",
    }
    translate = lambda key: translations.get(key, key)  # noqa: E731

    assert _source_label("PhishTank", translate) == "PhishTank"
    assert (
        _source_label("reconstructed/current_frozen/native_external", translate)
        == "Recovered external sources"
    )


@pytest.mark.parametrize(
    ("source", "source_type", "family"),
    [
        ("kaggle_multilingual_spam", "", "file"),
        ("common-crawl-bigdata", "", "bigdata"),
        ("synthetic-generated-common-crawl-signal", "", "bigdata"),
        ("database/faker/synthetic_spam", "", "database"),
        ("sap-labs-blog", "", "scraping"),
        ("PhishTank", "api", "api"),
        ("SEKOIA Community IOC", "scraping", "scraping"),
    ],
)
def test_dataset_sources_map_to_certification_families(
    source: str, source_type: str, family: str
) -> None:
    assert _source_family(source, source_type) == family


def test_frozen_source_distribution_is_validated(tmp_path: Path) -> None:
    metadata = tmp_path / "metadata.json"
    metadata.write_text(
        json.dumps(
            {
                "source_distribution": {
                    "kaggle_multilingual_spam": 4,
                    "ignored_zero": 0,
                    "ignored_text": "2",
                }
            }
        ),
        encoding="utf-8",
    )

    assert _load_frozen_source_distribution(metadata) == {"kaggle_multilingual_spam": 4}


def test_dataset_family_rows_conserve_frozen_base_and_add_live_lineage() -> None:
    sources = [
        {
            "name": "reconstructed/current_frozen/native_external",
            "source_type": "manual",
            "total_records": 6,
        },
        {"name": "PhishTank", "source_type": "api", "total_records": 3},
        {"name": "SEKOIA Community IOC", "source_type": "scraping", "total_records": 2},
    ]
    frozen = {
        "kaggle_multilingual_spam": 4,
        "common-crawl-bigdata": 1,
        "sap-labs-blog": 1,
    }

    rows = _source_family_rows(sources, frozen)
    totals = {row["family"]: row["count"] for row in rows}

    assert totals == {"file": 4, "api": 3, "scraping": 3, "bigdata": 1}
    assert sum(totals.values()) == sum(frozen.values()) + 5


def test_presentation_formatting_preserves_existing_contract() -> None:
    """Formatting helpers retain the values expected by Streamlit pages."""
    assert format_number(12345) == "12 345"
    assert format_number(12.5) == "12.50"
    assert safe_text("  hello\nworld  ") == "hello world"
    assert safe_text("abcdef", max_len=5) == "abcd..."
    assert remove_links("Ouvrir https://example.test/path maintenant") == (
        "Ouvrir [LIEN DÉSACTIVÉ] maintenant"
    )
    assert hash_token("token") == (
        "3c469e9d6c5875d37a43f353d4f88e61fcf812c66eee3457465a40b0da4153e0"
    )


def test_event_display_values_apply_only_supported_overrides() -> None:
    """Safety overrides do not erase the classifier's original label."""
    event = {
        "safety_verdict": "phishing",
        "label_verdict": "spam",
        "override_verdict": "safe",
    }
    assert effective_verdict(event) == "safe"
    assert effective_label(event) == "spam"
    assert effective_verdict({}) == "safe"
    assert effective_label({}) == "legitimate"


def test_translator_initializes_and_updates_language(tmp_path: Path) -> None:
    """URL language state is normalized and translated with French fallback."""
    path = tmp_path / "i18n.json"
    path.write_text(
        json.dumps({"fr": {"hello": "Bonjour"}, "en": {"hello": "Hello"}}),
        encoding="utf-8",
    )
    translator = PocTranslator(path)
    session: dict[str, object] = {}
    query: dict[str, object] = {"lang": ["en"]}

    translator.initialize(session, query)
    assert session["lang"] == "en"
    assert translator.translate("hello", "en") == "Hello"
    assert translator.translate("missing", "en") == "missing"

    translator.set_language("unexpected", session, query)
    assert session["lang"] == "fr"
    assert query["lang"] == "fr"


def test_translator_uses_fallback_when_file_is_absent(tmp_path: Path) -> None:
    """A missing translation file leaves the POC bootable."""
    translator = PocTranslator(tmp_path / "missing.json")
    assert translator.translate("title", "en") == "Sicurre"


def test_theme_preference_is_validated_and_persisted() -> None:
    """Theme state survives reload through a bounded URL preference."""
    session: dict[str, object] = {}
    query: dict[str, object] = {"theme": ["Dark"]}

    assert initialize_theme(session, query) == "Dark"
    assert session["theme_mode"] == "Dark"
    assert set_theme("Light", session, query) == "Light"
    assert query["theme"] == "Light"
    assert set_theme("unknown", session, query) == "System"


def test_theme_stylesheet_injects_override_at_explicit_marker(tmp_path: Path) -> None:
    """Theme CSS is loaded from an asset without leaking its contract marker."""
    path = tmp_path / "poc.css"
    path.write_text("before\n__THEME_OVERRIDE__\nafter", encoding="utf-8")

    rendered = load_theme_css(path, ":root { --bg: black; }")

    assert rendered == "before\n:root { --bg: black; }\nafter"
    assert "__THEME_OVERRIDE__" not in rendered


def test_theme_stylesheet_rejects_missing_override_marker(tmp_path: Path) -> None:
    """A malformed theme asset fails clearly instead of silently losing overrides."""
    path = tmp_path / "poc.css"
    path.write_text(":root {}", encoding="utf-8")

    with pytest.raises(ValueError, match="Missing theme override marker"):
        load_theme_css(path)


def test_home_metrics_distinguish_safety_and_classifier_quality() -> None:
    """Home evidence separates remediation outcomes from model labels."""
    events = [
        {
            "safety_verdict": "phishing",
            "label_verdict": "phishing",
            "expected_label": "phishing",
            "latency_ms": 100,
        },
        {
            "safety_verdict": "safe",
            "label_verdict": "spam",
            "expected_label": "phishing",
            "latency_ms": 200,
        },
        {
            "safety_verdict": "phishing",
            "label_verdict": "spam",
            "expected_label": "spam",
            "override_verdict": "safe",
            "latency_ms": 300,
        },
    ]

    metrics = calculate_home_metrics(events)
    assert metrics.total == 3
    assert metrics.blocked == 1
    assert metrics.delivered == 2
    assert metrics.spam_safe == 2
    assert metrics.false_positives == 0
    assert metrics.false_negatives == 1
    assert metrics.label_accuracy == pytest.approx(66.67, rel=0.01)
    assert metrics.latency_p95_ms == 200


def test_remediation_partitions_delivered_mail_and_honors_overrides() -> None:
    """SMail exposes eligible delivered messages under their classifier label."""
    events = [
        {"id": "1", "safety_verdict": "safe", "label_verdict": "legitimate", "context": "smail"},
        {"id": "2", "safety_verdict": "safe", "label_verdict": "spam", "context": "playground"},
        {
            "id": "3",
            "safety_verdict": "phishing",
            "label_verdict": "phishing",
            "override_verdict": "safe",
            "context": "manual",
        },
        {"id": "4", "safety_verdict": "safe", "label_verdict": "spam", "context": "worker"},
    ]
    inbox, spam = partition_delivered_events(events)
    assert [event["id"] for event in inbox] == ["1", "3"]
    assert [event["id"] for event in spam] == ["2"]


def test_threat_filter_uses_effective_verdict_and_period() -> None:
    """Threat history includes corrected misses and excludes corrected blocks."""
    now = datetime(2026, 7, 14, 12, tzinfo=UTC)
    events = [
        {"id": "recent", "safety_verdict": "phishing", "created_at": "2026-07-14T10:00:00+00:00"},
        {"id": "old", "safety_verdict": "phishing", "created_at": "2026-07-01T10:00:00+00:00"},
        {
            "id": "corrected-miss",
            "safety_verdict": "safe",
            "override_verdict": "phishing",
            "created_at": "2026-07-14T11:00:00+00:00",
        },
        {
            "id": "corrected-block",
            "safety_verdict": "phishing",
            "override_verdict": "safe",
            "created_at": "2026-07-14T11:00:00+00:00",
        },
    ]
    assert [event["id"] for event in filter_threats(events, "today", now)] == [
        "recent",
        "corrected-miss",
    ]
    assert [event["id"] for event in filter_threats(events, "all", now)] == [
        "recent",
        "old",
        "corrected-miss",
    ]


@pytest.mark.parametrize(
    ("safety", "label", "expected_key"),
    [
        ("phishing", "phishing", "class_phishing"),
        ("safe", "spam", "class_spam"),
        ("safe", "legitimate", "class_legitimate"),
    ],
)
def test_result_style_uses_safety_before_classifier_label(
    safety: str, label: str, expected_key: str
) -> None:
    """Blocked safety verdicts take precedence over the three-class label."""
    assert (
        result_style({"safety_verdict": safety, "label_verdict": label}).label_key == expected_key
    )


def test_confidence_bar_bounds_visual_width_without_changing_evidence() -> None:
    """Malformed confidence cannot overflow the result layout."""
    assert "width:100.0%" in confidence_bar("Phishing", 120.0, "#DC2626")
    assert "120 %" in confidence_bar("Phishing", 120.0, "#DC2626")
    assert "width:0.0%" in confidence_bar("Legitimate", -4.0, "#047857")


def test_terminal_output_redacts_common_secret_assignments() -> None:
    """Pipeline evidence cannot echo common credential formats."""
    assert redact_terminal_line("API_KEY=super-secret next") == "API_KEY=[REDACTED] next"
    assert redact_terminal_line("token: abc123") == "token=[REDACTED]"
    assert redact_terminal_line("processed 42 records") == "processed 42 records"
