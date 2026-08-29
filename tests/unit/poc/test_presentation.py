"""Unit tests for testable POC presentation services."""

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
import streamlit as st

from poc.presentation.admin import (
    _check_readiness,
    _inference_readiness,
    _ingestion_status,
    _render_classification_chart,
)
from poc.presentation.datasets import (
    _aggregate_initialization_runs,
    _load_frozen_source_distribution,
    _local_run_time,
    _reference_provider_rows,
    _render_source_stage_chart,
    _run_fetch_counts,
    _source_family,
    _source_label,
    _source_stage_rows,
    _training_provider_rows,
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
from poc.presentation.playground import _run_inference
from poc.presentation.remediation import (
    _dismiss_confirmation,
    _render_completed_notice,
    _request_confirmation,
    clear_stale_confirmation,
    filter_threats,
    paginate_threats,
    partition_delivered_events,
)
from poc.presentation.result import confidence_bar, result_style
from poc.presentation.theme import initialize_theme, load_theme_css, set_theme
from poc.presentation.theme_overrides import get_theme_override_css
from poc.runtime_preflight import RuntimeCheck


def test_admin_readiness_statuses_are_text_backed_and_semantic() -> None:
    """Readiness colors supplement explicit ready, attention, and blocking text."""
    labels = {
        "preflight_ready": "Prêt",
        "preflight_attention": "À vérifier",
        "preflight_blocking": "Bloquant",
        "admin_ingestion_completed": "Terminée",
        "admin_ingestion_running": "En cours",
        "admin_ingestion_failed": "Échec",
        "admin_unavailable": "indisponible",
    }
    translate = lambda key: labels.get(key, key)  # noqa: E731

    assert _check_readiness(RuntimeCheck("ready", True, True), translate) == (
        "ready",
        "Prêt",
    )
    assert _check_readiness(RuntimeCheck("optional", False, False), translate) == (
        "attention",
        "À vérifier",
    )
    assert _check_readiness(RuntimeCheck("required", False, True), translate) == (
        "blocking",
        "Bloquant",
    )
    assert _inference_readiness("ready", translate) == ("ready", "Prêt")
    assert _inference_readiness("contract_invalid", translate) == (
        "attention",
        "À vérifier",
    )
    assert _inference_readiness("unreachable", translate) == ("blocking", "Bloquant")
    assert _ingestion_status("completed", translate) == ("ready", "Terminée")
    assert _ingestion_status("running", translate) == ("attention", "En cours")
    assert _ingestion_status("failed", translate) == ("blocking", "Échec")


def test_admin_classification_chart_uses_distinct_integer_ticks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Small class totals must not render duplicate rounded half-step labels."""
    rendered: dict[str, object] = {}

    def capture_chart(rows: object, specification: object, **kwargs: object) -> None:
        rendered.update(rows=rows, specification=specification, kwargs=kwargs)

    monkeypatch.setattr(st, "vega_lite_chart", capture_chart)
    snapshot = SimpleNamespace(
        classifications=SimpleNamespace(legitimate=1, spam=2, phishing=3)
    )

    _render_classification_chart(snapshot, lambda key: key)

    specification = rendered["specification"]
    assert isinstance(specification, dict)
    axis = specification["encoding"]["x"]["axis"]
    assert axis["format"] == ",d"
    assert axis["tickMinStep"] == 1


def test_dataset_source_labels_preserve_real_sources_and_shorten_reconstruction() -> None:
    """Recovered provenance remains readable without disguising real source names."""
    translations = {
        "reconstructed_source_native_external": "Recovered external sources",
    }
    translate = lambda key: translations.get(key, key)  # noqa: E731

    translations["source_provider_phishtank"] = "PhishTank API"
    assert _source_label("PhishTank API (rejeu local)", translate) == "PhishTank API"
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


def test_dataset_runs_collapse_baseline_and_keep_incremental_sources() -> None:
    """The selector exposes one V1 operation followed by real source runs."""
    runs = [
        {
            "id": "base-a",
            "name": "reconstructed/current_frozen/native_external",
            "raw_object_count": 1,
            "raw_record_count": 6,
            "normalized_count": 6,
            "dataset_item_count": 6,
            "started_at": "2026-01-01T10:00:00Z",
            "finished_at": "2026-01-01T10:01:00Z",
        },
        {
            "id": "base-b",
            "name": "reconstructed/current_frozen/synthetic_db",
            "raw_object_count": 1,
            "raw_record_count": 4,
            "normalized_count": 4,
            "dataset_item_count": 4,
            "started_at": "2026-01-01T10:00:00Z",
            "finished_at": "2026-01-01T10:01:00Z",
        },
        {
            "id": "phishtank",
            "name": "PhishTank API (rejeu local)",
            "trigger_mode": "poc_replay",
            "raw_object_count": 1,
            "raw_record_count": 3,
            "normalized_count": 0,
            "dataset_item_count": 0,
            "started_at": "2026-01-01T10:01:00Z",
            "finished_at": "2026-01-01T10:02:00Z",
        },
        {"id": "sekoia", "name": "sekoia-community-ioc", "raw_record_count": 3},
    ]

    displayed = _aggregate_initialization_runs(runs, lambda key: key)

    assert [row["id"] for row in displayed] == ["sekoia", "base-initialization"]
    assert displayed[-1]["raw_record_count"] == 13
    assert displayed[-1]["dataset_item_count"] == 10


def test_run_fetch_counts_use_source_metadata_without_double_counting() -> None:
    """SEKOIA source volume separates fetched, new, and deduplicated IOCs."""
    assert _run_fetch_counts(
        {
            "raw_record_count": 3,
            "source_metadata": json.dumps({"total_ioc_count": 10, "new_ioc_count": 3}),
        }
    ) == (10, 7)


def test_run_fetch_counts_use_log_for_fully_deduplicated_run() -> None:
    """A no-write replay still reports its fetched and skipped evidence."""
    assert _run_fetch_counts(
        {
            "raw_record_count": 0,
            "source_metadata": None,
            "log_message": "SEKOIA IOC feed returned 640 IOC(s); all were already ingested",
        }
    ) == (640, 640)


def test_dataset_provider_rows_separate_training_and_reference_evidence() -> None:
    sources = [
        {
            "name": "reconstructed/current_frozen/native_external",
            "source_type": "manual",
            "total_records": 6,
            "reference_records": 0,
        },
        {
            "name": "PhishTank API (rejeu local)",
            "source_type": "api",
            "total_records": 3,
            "reference_records": 3,
        },
        {
            "name": "sekoia-community-ioc",
            "source_type": "scraping",
            "total_records": 2,
            "reference_records": 2,
        },
    ]
    frozen = {"kaggle_multilingual_spam": 4, "common-crawl-bigdata": 1}

    training_totals = {row["provider"]: row["count"] for row in _training_provider_rows(frozen)}
    reference_totals = {
        row["provider"]: row["count"] for row in _reference_provider_rows(sources)
    }

    assert training_totals == {"kaggle": 4, "common_crawl": 1}
    assert reference_totals == {"phishtank": 3, "sekoia": 2}


def test_dataset_stage_rows_keep_each_provider_synchronized_across_stages() -> None:
    """One projection drives the raw, normalized, and dataset bars per source."""
    sources = [
        {
            "name": "reconstructed/current_frozen/native_external",
            "source_type": "manual",
            "total_records": 99,
            "reference_records": 0,
            "normalized_records": 99,
            "dataset_records": 99,
            "last_run": "2026-01-02T12:00:00Z",
        },
        {
            "name": "PhishTank API (rejeu local)",
            "source_type": "api",
            "total_records": 3,
            "reference_records": 3,
            "normalized_records": 0,
            "dataset_records": 0,
            "last_run": "2026-01-01T12:00:00Z",
        },
        {
            "name": "sekoia-community-ioc",
            "source_type": "scraping",
            "total_records": 2,
            "reference_records": 2,
            "normalized_records": 0,
            "dataset_records": 0,
        },
    ]
    rows = _source_stage_rows({"kaggle_multilingual_spam": 4}, sources)
    counts = {
        (row["provider"], row["stage"]): row["count"]
        for row in rows
    }

    assert counts[("kaggle", "raw")] == 4
    assert counts[("kaggle", "normalized")] == 4
    assert counts[("kaggle", "dataset")] == 4
    assert counts[("phishtank", "raw")] == 3
    assert counts[("phishtank", "normalized")] == 0
    assert counts[("sekoia", "dataset")] == 0
    assert not any(row["provider"] == "other" for row in rows)
    assert {
        row["last_run"] for row in rows if row["provider"] == "kaggle"
    } == {"2026-01-02T12:00:00Z"}


def test_source_stage_chart_uses_quiet_axes_and_truthful_tooltip(monkeypatch) -> None:
    """The grouped chart avoids repeated labels while retaining exact tooltips."""
    captured = {}
    monkeypatch.setitem(st.session_state, "theme_mode", "Dark")
    monkeypatch.setattr(
        st,
        "vega_lite_chart",
        lambda data, spec, **kwargs: captured.update(spec=spec),
    )

    _render_source_stage_chart(
        [
            {
                "provider": "phishtank",
                "family": "api",
                "role": "reference",
                "stage": "raw",
                "count": 1139,
                "raw_total": 1139,
                "last_run": None,
            }
        ],
        lambda key: key,
    )

    specification = captured["spec"]
    assert specification["mark"]["type"] == "bar"
    assert specification["encoding"]["x"]["axis"]["grid"] is False
    assert specification["encoding"]["x"]["axis"]["tickCount"] == 6
    assert "layer" not in specification
    assert specification["encoding"]["tooltip"][-1]["title"] == "last_local_update"


def test_run_time_formatting_handles_absent_and_legacy_values() -> None:
    """Incomplete legacy evidence remains readable without crashing the page."""
    assert _local_run_time(None) == "-"
    assert _local_run_time("legacy timestamp") == "legacy timestamp"


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


def test_poc_stylesheet_keeps_button_tooltips_high_contrast() -> None:
    """Button help must not inherit the low-contrast dropdown menu palette."""
    stylesheet = Path("src/poc/assets/poc.css").read_text(encoding="utf-8")

    assert '[role="tooltip"]' in stylesheet
    assert "background-color: #10243E !important" in stylesheet
    assert "color: #FFFFFF !important" in stylesheet


def test_poc_stylesheet_themes_dialogs_remediation_and_terminal_surfaces() -> None:
    """Critical POC interactions retain explicit contrast in both themes."""
    stylesheet = Path("src/poc/assets/poc.css").read_text(encoding="utf-8")

    assert '[role="dialog"]' in stylesheet
    assert '[data-baseweb="modal"] button[aria-label="Close"]' in stylesheet
    assert '[data-testid="stExpanderDetails"] [class*="st-key-fp_"] button' in stylesheet
    assert "background-color: var(--status-safe-bg) !important" in stylesheet
    assert "background-color: var(--status-danger-bg) !important" in stylesheet
    assert '[data-testid="stToast"]' in stylesheet
    assert "background-color: var(--status-safe-bg) !important" in stylesheet
    assert '[class*="st-key-delete_"] button:hover' in stylesheet
    assert "background-color: var(--neutral-hover-bg) !important" in stylesheet
    assert '[data-theme="dark"] [class*="st-key-fn_"]' not in stylesheet
    assert '[class*="st-key-fn_"] button:hover *' in stylesheet
    assert '[data-testid="stCode"]' in stylesheet
    assert ".poc-success-notice" in stylesheet
    assert "background-color: #050A12 !important" in stylesheet
    assert "border: 1px solid #60738F !important" in stylesheet
    assert "color: #DCE7F5 !important" in stylesheet


def test_poc_stylesheet_separates_semantic_and_table_tokens_by_theme() -> None:
    """Status pills and data grids must remain distinct in light and dark modes."""
    stylesheet = Path("src/poc/assets/poc.css").read_text(encoding="utf-8")

    assert '[data-theme="light"]' in stylesheet
    assert "--status-safe-border: #D7E9DE" in stylesheet
    assert "--status-safe-border: #276B57" in stylesheet
    assert "--table-border: #CBD5E1" in stylesheet
    assert "--table-border: #58718F" in stylesheet
    assert ".evidence-table th + th" in stylesheet
    assert "border-left: 1px solid var(--table-border)" in stylesheet
    assert "border-color: var(--status-safe-border)" in stylesheet


def test_poc_sidebar_navigation_uses_one_continuous_fill() -> None:
    """Navigation states must not combine a fill with a contrasting side stripe."""
    stylesheet = Path("src/poc/assets/poc.css").read_text(encoding="utf-8")

    assert "border-left: 3px solid" not in stylesheet
    assert "border-radius: 6px !important" in stylesheet


def test_forced_theme_overrides_streamlit_theme_containers() -> None:
    """A selected POC theme must win over Streamlit or OS theme attributes."""
    light = get_theme_override_css("Light")
    dark = get_theme_override_css("Dark")

    for override in (light, dark):
        assert '[data-theme="light"]' in override
        assert '[data-theme="dark"]' in override
        assert "--table-header-bg:" in override
        assert "--status-safe-bg:" in override
    assert "--table-header-bg: #EEF2F7 !important" in light
    assert "--status-safe-bg: #F7FBF8 !important" in light
    assert "--table-header-bg: #15243A !important" in dark


def test_pending_remediation_is_owned_by_one_page_and_cleared_on_dismissal() -> None:
    """Native dismissal and navigation cannot leave a stale action behind."""
    _request_confirmation("delete", "event-1", "nav_smail")
    assert st.session_state["pending_remediation"]["surface"] == "nav_smail"

    clear_stale_confirmation("nav_smail")
    assert "pending_remediation" in st.session_state
    clear_stale_confirmation("nav_home")
    assert "pending_remediation" not in st.session_state

    _request_confirmation("delete", "event-2", "nav_smail")
    _dismiss_confirmation()
    assert "pending_remediation" not in st.session_state


def test_remediation_completion_notice_is_concise_and_icon_free(monkeypatch) -> None:
    """Confirmed remediation uses one accessible text-only success notice."""
    notices: list[tuple[tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setitem(st.session_state, "remediation_completed", "delete")
    monkeypatch.setattr(
        st,
        "toast",
        lambda *args, **kwargs: notices.append((args, kwargs)),
    )

    _render_completed_notice(
        lambda key: "Message supprimé." if key == "remediation_delete_done" else key
    )

    assert notices == [(('Message supprimé.',), {})]
    assert "remediation_completed" not in st.session_state


def test_failed_playground_inference_is_not_persisted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persisted: list[dict[str, object]] = []

    class Spinner:
        def __enter__(self) -> None:
            return None

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(st, "spinner", lambda _label: Spinner())
    monkeypatch.setattr(st, "rerun", lambda: pytest.fail("failed inference reran the app"))

    _run_inference(
        subject="Test local",
        sender="probe@sicurre.test",
        text="Corps synthétique",
        expected_label=None,
        context="playground",
        user_email="admin@example.test",
        use_llm=False,
        use_virustotal=False,
        classify=lambda *_args, **_kwargs: None,
        persist=lambda **evidence: persisted.append(evidence),
        translate=lambda key: key,
    )

    assert persisted == []


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
    assert metrics.latency_p95_ms == 300


def test_home_latency_uses_only_real_successful_inference() -> None:
    events = [
        {"latency_ms": 120, "inference_source": "live"},
        {"latency_ms": 900, "inference_source": "simulation"},
        {"latency_ms": 0, "inference_source": "live"},
    ]
    assert calculate_home_metrics(events).latency_p95_ms == 120


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


def test_threat_pagination_is_bounded_and_clamps_stale_pages() -> None:
    """Threat history exposes stable pages instead of truncating or scrolling forever."""
    events = [{"id": str(index)} for index in range(23)]

    first, first_page, total_pages = paginate_threats(events, 1)
    last, last_page, _ = paginate_threats(events, 99)

    assert [event["id"] for event in first] == [str(index) for index in range(10)]
    assert (first_page, total_pages) == (1, 3)
    assert [event["id"] for event in last] == ["20", "21", "22"]
    assert last_page == 3


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
