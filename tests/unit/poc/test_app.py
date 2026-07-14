"""Streamlit interaction tests for the local certification POC."""

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


@pytest.fixture
def poc_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AppTest:
    """Run the real POC script against isolated local configuration."""
    auth_path = tmp_path / "poc-auth.db"
    data_path = tmp_path / "poc-data.db"
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
