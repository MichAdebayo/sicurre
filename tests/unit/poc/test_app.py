import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from poc import config, local_runtime

APP_PATH = Path(__file__).resolve().parents[3] / "src" / "poc" / "app.py"


def login(app: AppTest) -> None:
    """Authenticate the isolated administrator account."""
    app.text_input[0].input("admin@example.test")
    app.text_input[1].input("admin-password")
    app.button[0].click().run()


def open_page(app: AppTest, label: str, page_key: str) -> None:
    """Navigate through the real sidebar and settle Streamlit's rerun."""
    next(button for button in app.button if button.label == label).click().run()
    app.run()
    assert app.session_state["page"] == page_key


def _seed_data_evidence(data_path: Path) -> None:
    conn = sqlite3.connect(str(data_path))
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS data_source_system (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                source_type TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS data_ingestion_run (
                id TEXT PRIMARY KEY,
                source_system_id TEXT NOT NULL,
                raw_record_count INTEGER NOT NULL,
                finished_at TEXT NOT NULL,
                status TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS data_dataset (
                version_tag TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                item_count INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS data_raw_record "
            "(id TEXT PRIMARY KEY, source_system_id TEXT)"
        )
        conn.execute("CREATE TABLE IF NOT EXISTS data_normalized_message (id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE IF NOT EXISTS data_dataset_item (id TEXT PRIMARY KEY)")

        # Seed data
        conn.execute(
            "INSERT INTO data_source_system (id, name, source_type) VALUES ('ss-1', 'PhishTank', 'api')"
        )
        conn.execute(
            "INSERT INTO data_source_system (id, name, source_type) VALUES ('ss-2', 'CERT-FR', 'scraping')"
        )
        conn.execute(
            "INSERT INTO data_source_system (id, name, source_type) VALUES "
            "('ss-3', 'reconstructed/current_frozen/native_external', 'manual')"
        )
        conn.execute(
            "INSERT INTO data_ingestion_run (id, source_system_id, raw_record_count, finished_at, status) VALUES ('ir-1', 'ss-1', 100, '2026-07-15T12:00:00Z', 'success')"
        )
        conn.execute(
            "INSERT INTO data_ingestion_run (id, source_system_id, raw_record_count, finished_at, status) VALUES ('ir-2', 'ss-2', 50, '2026-07-15T13:00:00Z', 'success')"
        )
        conn.execute(
            "INSERT INTO data_dataset (version_tag, status, item_count, created_at) VALUES ('base-20260715', 'frozen', 120, '2026-07-15T14:00:00Z')"
        )
        conn.execute(
            "INSERT INTO data_raw_record (id, source_system_id) "
            "VALUES ('1', 'ss-1'), ('2', 'ss-2'), ('3', 'ss-3')"
        )
        conn.execute("INSERT INTO data_normalized_message (id) VALUES ('1'), ('2')")
        conn.execute("INSERT INTO data_dataset_item (id) VALUES ('1'), ('2')")
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def poc_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    """Run the real POC script against isolated local configuration."""
    auth_path = tmp_path / "poc-auth.db"
    data_path = tmp_path / "poc-data.db"
    _seed_data_evidence(data_path)

    # Mock stream_operation to avoid running actual make commands during tests
    def mock_stream_operation(operation_key: str, settings: object) -> Iterator[str]:
        if st_session_state := getattr(pytest, "_pipeline_fail_type", None):
            if st_session_state == "permission":
                raise PermissionError("Access denied")
            raise RuntimeError("Generic crash")
        yield "Starting task...\n"
        yield "Processing record 1...\n"
        yield "API_KEY=mysecret\n"
        yield "Done.\n"

    from poc.presentation import pipeline_page

    monkeypatch.setattr(pipeline_page, "stream_operation", mock_stream_operation)

    environment = {
        "SICURRE_POC_DATABASE_URL": f"sqlite+aiosqlite:///{auth_path}",
        "SICURRE_POC_DATA_PLATFORM_DATABASE_URL": f"sqlite+aiosqlite:///{data_path}",
        "SICURRE_POC_INFERENCE_API_URL": "http://127.0.0.1:9/v1/classify",
        "SICURRE_POC_INFERENCE_API_KEY": "poc-test-key",
        "SICURRE_POC_ADMIN_EMAIL": "admin@example.test",
        "SICURRE_POC_ADMIN_PASSWORD": "admin-password",
        "SICURRE_POC_ADMIN_NAME": "Admin Test",
        "SICURRE_POC_VIEWER_EMAIL": "viewer@example.test",
        "SICURRE_POC_VIEWER_PASSWORD": "viewer-password",
        "SICURRE_POC_VIEWER_NAME": "Viewer Test",
    }
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    config.get_poc_settings.cache_clear()
    settings = config.get_poc_settings()
    monkeypatch.setattr(local_runtime, "SETTINGS", settings)
    monkeypatch.setattr(local_runtime, "POC_AUTH_DB_PATH", auth_path)
    monkeypatch.setattr(local_runtime, "POC_DATA_DB_PATH", data_path)
    monkeypatch.setattr(local_runtime, "DEFAULT_ADMIN_EMAIL", settings.admin_email)
    monkeypatch.setattr(local_runtime, "DEFAULT_ADMIN_PASSWORD", settings.admin_password)
    monkeypatch.setattr(local_runtime, "DEFAULT_ADMIN_NAME", settings.admin_name)
    monkeypatch.setattr(local_runtime, "DEFAULT_VIEWER_EMAIL", settings.viewer_email)
    monkeypatch.setattr(local_runtime, "DEFAULT_VIEWER_PASSWORD", settings.viewer_password)
    monkeypatch.setattr(local_runtime, "DEFAULT_VIEWER_NAME", settings.viewer_name)
    app = AppTest.from_file(str(APP_PATH), default_timeout=10)
    app.run()
    assert not app.exception
    return app


def test_invalid_and_valid_login_are_contextual(poc_app: AppTest) -> None:
    poc_app.text_input[0].input("missing@example.test")
    poc_app.text_input[1].input("wrong-password")
    poc_app.button[0].click().run()
    assert any("Identifiants invalides" in warning.value for warning in poc_app.warning)

    poc_app.text_input[0].input("admin@example.test")
    poc_app.text_input[1].input("admin-password")
    poc_app.button[0].click().run()
    assert not poc_app.exception
    assert poc_app.session_state["authenticated"] is True
    assert poc_app.session_state["user"]["display_name"] == "Admin Test"


def test_controlled_incident_is_visible_and_not_persisted(poc_app: AppTest) -> None:
    login(poc_app)
    open_page(poc_app, "Espace d'essai", "nav_playground")
    poc_app.button_group[0].set_value("incident").run()
    analyze = next(button for button in poc_app.button if button.label == "Analyser l'email")
    analyze.click().run()

    assert any("Classification impossible" in error.value for error in poc_app.error)
    assert "last_result" in poc_app.session_state
    assert poc_app.session_state["last_result"] is None


def test_successful_simulation_populates_operational_pages(poc_app: AppTest) -> None:
    login(poc_app)
    open_page(poc_app, "Espace d'essai", "nav_playground")
    poc_app.button_group[0].set_value("simulation").run()
    next(button for button in poc_app.button if button.label == "Analyser l'email").click().run()
    poc_app.run()

    result = poc_app.session_state["last_result"]
    assert result["source"] == "simulation"
    assert result["label_verdict"] == "phishing"

    analyze_buttons = [button for button in poc_app.button if button.label == "Analyser l'email"]
    assert len(analyze_buttons) == 2
    analyze_buttons[1].click().run()
    poc_app.run()
    assert poc_app.session_state["last_result"]["source"] == "simulation"

    open_page(poc_app, "Accueil", "nav_home")
    assert any("URGENT" in markdown.value for markdown in poc_app.markdown)

    open_page(poc_app, "Journal des menaces", "nav_threat_log")
    assert poc_app.selectbox
    assert any("URGENT" in markdown.value for markdown in poc_app.markdown)

    open_page(poc_app, "Jeux de données", "nav_datasets")
    assert not poc_app.exception

    open_page(poc_app, "Flux de données", "nav_pipeline")
    assert any(button.label == "Reconstruire la base" for button in poc_app.button)

    open_page(poc_app, "Paramètres", "nav_settings")
    assert len(poc_app.selectbox) == 2


def test_false_positive_correction_delivers_message_to_smail(poc_app: AppTest) -> None:
    """A blocked message corrected as safe becomes visible in the local inbox."""
    login(poc_app)
    open_page(poc_app, "Espace d'essai", "nav_playground")
    poc_app.button_group[0].set_value("simulation").run()
    next(button for button in poc_app.button if button.label == "Analyser l'email").click().run()
    poc_app.run()

    open_page(poc_app, "Journal des menaces", "nav_threat_log")
    mark_safe = next(button for button in poc_app.button if button.label == "Marquer faux positif")
    mark_safe.click().run()
    poc_app.run()

    open_page(poc_app, "Smail", "nav_smail")
    assert any("URGENT" in markdown.value for markdown in poc_app.markdown)


def test_false_negative_report_moves_delivered_message_to_threat_log(poc_app: AppTest) -> None:
    """A delivered message reported as phishing becomes visible in threat history."""
    login(poc_app)
    open_page(poc_app, "Espace d'essai", "nav_playground")
    poc_app.button_group[0].set_value("simulation").run()
    poc_app.selectbox[0].set_value("Client facture").run()
    next(button for button in poc_app.button if button.label == "Analyser l'email").click().run()
    poc_app.run()

    open_page(poc_app, "Smail", "nav_smail")
    report = next(button for button in poc_app.button if button.label == "Signaler comme phishing")
    report.click().run()
    poc_app.run()

    open_page(poc_app, "Journal des menaces", "nav_threat_log")
    assert any("Validation facture mars" in markdown.value for markdown in poc_app.markdown)


def test_pipeline_and_datasets_pages(poc_app: AppTest) -> None:
    """Test successful and failing pipeline runs, observer warning, and datasets display."""
    login(poc_app)

    # 1. Test Datasets Page (showing metrics and seeded database)
    open_page(poc_app, "Jeux de données", "nav_datasets")
    assert not poc_app.exception
    # Verify seeded counts are shown
    assert any("base-20260715" in md.value for md in poc_app.markdown)
    assert any("PhishTank" in md.value for md in poc_app.markdown)
    assert any("base V1 récupérée" in caption.value for caption in poc_app.caption)

    # 2. Test Pipeline Page - Admin Successful Run
    open_page(poc_app, "Flux de données", "nav_pipeline")
    assert any("préfixe R2 demonstrations/poc" in caption.value for caption in poc_app.caption)
    assert any("Aucun envoi Kaggle" in caption.value for caption in poc_app.caption)
    cron_btn = next(btn for btn in poc_app.button if btn.label == "Cron incrémental")
    cron_btn.click().run()
    assert not poc_app.exception
    assert any("Dernière opération terminée avec succès" in info.value for info in poc_app.info)

    # 3. Test Pipeline Page - Permission Error Handler
    pytest._pipeline_fail_type = "permission"  # type: ignore[attr-defined]
    cron_btn.click().run()
    assert not poc_app.exception
    assert any("Dernière opération en erreur" in warning.value for warning in poc_app.warning)

    # 4. Test Pipeline Page - General Error Handler
    pytest._pipeline_fail_type = "runtime"  # type: ignore[attr-defined]
    cron_btn.click().run()
    assert not poc_app.exception
    assert any("Dernière opération en erreur" in warning.value for warning in poc_app.warning)
    pytest._pipeline_fail_type = None  # type: ignore[attr-defined]

    # 5. Test Pipeline Page - Observer Restriction
    # Logout and login as viewer/observer
    open_page(poc_app, "Paramètres", "nav_settings")
    logout_btn = next(btn for btn in poc_app.button if btn.label == "Déconnexion")
    logout_btn.click().run()
    assert poc_app.session_state["authenticated"] is False

    poc_app.text_input[0].input("viewer@example.test")
    poc_app.text_input[1].input("viewer-password")
    poc_app.button[0].click().run()
    assert poc_app.session_state["authenticated"] is True
    assert poc_app.session_state["user"]["role"] == "viewer"

    open_page(poc_app, "Flux de données", "nav_pipeline")
    assert any("Accès réservé" in warning.value for warning in poc_app.warning)
