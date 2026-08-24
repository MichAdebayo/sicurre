from __future__ import annotations

from collections.abc import MutableMapping
from pathlib import Path
from typing import Any, cast

import streamlit as st

from poc.authentication import PocAuthStore
from poc.config import get_poc_settings
from poc.data_evidence import PocDataEvidenceStore
from poc.events import PocEventStore
from poc.inference import (
    ClassificationRequest,
    InferenceMode,
    PocInferenceClient,
    PocInferenceError,
)
from poc.local_runtime import POC_AUTH_DB_PATH, POC_DATA_DB_PATH, ensure_local_auth_db
from poc.presentation.datasets import render_datasets
from poc.presentation.home import render_home
from poc.presentation.i18n import PocTranslator
from poc.presentation.pipeline_page import execute_pipeline_action, render_pipeline_page
from poc.presentation.playground import render_playground
from poc.presentation.remediation import render_smail, render_threat_log
from poc.presentation.resilience import render_resilience
from poc.presentation.result import render_inference_result
from poc.presentation.settings import render_settings
from poc.presentation.shell import render_login, render_sidebar
from poc.presentation.theme import initialize_theme, load_theme_css, set_theme
from poc.presentation.theme_overrides import get_theme_override_css
from poc.runtime_preflight import blocking_failures, build_runtime_checks
from poc.session import PocSessionController

POC_SETTINGS = get_poc_settings()
STARTUP_ERROR: str | None = None
try:
    POC_SETTINGS.require_demo_credentials()
    ensure_local_auth_db()
except RuntimeError as error:
    STARTUP_ERROR = str(error)
INFERENCE_CLIENT = PocInferenceClient(POC_SETTINGS)
AUTH_STORE = PocAuthStore(POC_AUTH_DB_PATH)
DATA_EVIDENCE_STORE = PocDataEvidenceStore(POC_DATA_DB_PATH)
EVENT_STORE = PocEventStore(AUTH_STORE)
SESSION_STATE = cast(MutableMapping[str, Any], st.session_state)
QUERY_PARAMS = cast(MutableMapping[str, Any], st.query_params)
SESSION_CONTROLLER = PocSessionController(AUTH_STORE, SESSION_STATE, QUERY_PARAMS)

ROOT_DIR = Path(__file__).resolve().parents[2]
I18N_PATH = ROOT_DIR / "src" / "poc" / "i18n.json"
LOGO_PATH = ROOT_DIR / "src" / "app" / "assets" / "sicurre.svg"

INFERENCE_URL = POC_SETTINGS.inference_api_url
INFERENCE_API_KEY = POC_SETTINGS.inference_api_key

# ── Dynamic Theme Mode Override ──────────────────────────────────────────────
theme_mode = initialize_theme(SESSION_STATE, QUERY_PARAMS)
force_theme_css = get_theme_override_css(theme_mode)

st.set_page_config(
    page_title="Sicurre - POC",
    page_icon="S",
    layout="wide",
    initial_sidebar_state="auto",
)

st.markdown(
    f"<style>{load_theme_css(ROOT_DIR / 'src' / 'poc' / 'assets' / 'poc.css', force_theme_css)}</style>",
    unsafe_allow_html=True,
)


DEMO_EMAILS: list[dict[str, str]] = [
    {
        "name": "RIB urgent",
        "sender": "ceo@entreprise-france.com",
        "subject": "URGENT - changement de RIB fournisseur",
        "text": "Bonjour, paiement urgent. Merci d'envoyer aujourd'hui le virement sur ce nouveau compte en PJ.",
        "expected_label": "phishing",
    },
    {
        "name": "Mise a jour compte",
        "sender": "security@impots-gouv-fr.co",
        "subject": "Confirmez votre identite sous 24h",
        "text": "Votre espace fiscal sera suspendu. Cliquez et confirmez votre mot de passe immediatement.",
        "expected_label": "phishing",
    },
    {
        "name": "Facture cloud",
        "sender": "billing@host-france.io",
        "subject": "Facture impayee - action requise",
        "text": "Nous avons detecte un incident de facturation. Ouvrez la facture securisee et reglez dans la journee.",
        "expected_label": "phishing",
    },
    {
        "name": "Promo webinaire",
        "sender": "growth@marketing-hub.io",
        "subject": "Multipliez vos ventes en 7 jours",
        "text": "Formation gratuite, bonus limite, methode secrete pour doubler votre chiffre d'affaires.",
        "expected_label": "spam",
    },
    {
        "name": "Offre B2B",
        "sender": "offers@pro-distribution.biz",
        "subject": "Pack entreprise - remise 65% aujourd'hui",
        "text": "Offre exceptionnelle reservee a votre societe, validez votre commande avant minuit.",
        "expected_label": "spam",
    },
    {
        "name": "Cold outreach",
        "sender": "contact@smart-leads.ai",
        "subject": "On booste vos leads cette semaine",
        "text": "Nous avons prepare un plan en 3 etapes pour multiplier vos prospects qualifies.",
        "expected_label": "spam",
    },
    {
        "name": "Client facture",
        "sender": "client@atelier-dupont.fr",
        "subject": "Validation facture mars",
        "text": "Bonjour, pouvez-vous verifier la facture de mars et me confirmer le bon de commande associe ?",
        "expected_label": "legitimate",
    },
    {
        "name": "Comptable",
        "sender": "compta@moncabinet.fr",
        "subject": "Pieces comptables T1",
        "text": "Merci de deposer les justificatifs du trimestre dans l'espace partage avant vendredi.",
        "expected_label": "legitimate",
    },
    {
        "name": "Agenda client",
        "sender": "noreply@calendrier-pro.fr",
        "subject": "Rappel rendez-vous demain",
        "text": "Rappel: rendez-vous avec votre client demain a 10h. Repondez si vous souhaitez deplacer le creneau.",
        "expected_label": "legitimate",
    },
]


_TRANSLATOR = PocTranslator(I18N_PATH)
_TRANSLATOR.initialize(SESSION_STATE, QUERY_PARAMS)


def tr(key: str) -> str:
    return _TRANSLATOR.translate(key, st.session_state.get("lang", "fr"))


def _set_lang(lang: str) -> None:
    _TRANSLATOR.set_language(lang, SESSION_STATE, QUERY_PARAMS)


def _set_theme(theme: str) -> None:
    set_theme(theme, SESSION_STATE, QUERY_PARAMS)


def authenticate_user(email: str, password: str) -> dict[str, Any] | None:
    return AUTH_STORE.authenticate(email, password)


def update_display_name(user_id: str, display_name: str) -> None:
    """Persist a local POC profile name through the auth store boundary."""
    AUTH_STORE.execute("UPDATE poc_user SET display_name = ? WHERE id = ?", (display_name, user_id))


def inference_status() -> tuple[bool, str]:
    healthy, status_key = INFERENCE_CLIENT.health()
    return healthy, tr(status_key)


def classify_email(
    subject: str,
    sender: str,
    text_value: str,
    use_llm: bool = True,
    use_virustotal: bool = True,
) -> dict[str, Any]:
    mode = InferenceMode(st.session_state.get("inference_mode", InferenceMode.LIVE.value))
    return INFERENCE_CLIENT.classify(
        ClassificationRequest(
            subject=subject,
            sender=sender,
            text=text_value,
            use_llm=use_llm,
            use_virustotal=use_virustotal,
        ),
        mode=mode,
    )


def classify_email_for_ui(
    subject: str,
    sender: str,
    text_value: str,
    use_llm: bool = True,
    use_virustotal: bool = True,
) -> dict[str, Any] | None:
    """Run classification and present a controlled, actionable failure."""
    try:
        return classify_email(subject, sender, text_value, use_llm, use_virustotal)
    except PocInferenceError as exc:
        st.session_state["last_result"] = None
        st.session_state["last_inference_error"] = str(exc)
        st.error(f"{tr('inference_request_failed')} {exc}")
        return None


def reclassify_event(event_id: str, new_verdict: str, by_user: str) -> None:
    """Override the safety verdict for a single event."""
    EVENT_STORE.reclassify(event_id, new_verdict, by_user)


if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "show_login" not in st.session_state:
    st.session_state["show_login"] = True
if "last_result" not in st.session_state:
    st.session_state["last_result"] = None
if "page" not in st.session_state:
    st.session_state["page"] = "nav_home"

SESSION_CONTROLLER.restore()

if STARTUP_ERROR:
    startup_checks = build_runtime_checks(
        POC_SETTINGS,
        POC_AUTH_DB_PATH,
        POC_DATA_DB_PATH,
        inference_ready=False,
    )
    st.error(tr("preflight_blocked"))
    for check in blocking_failures(startup_checks):
        st.markdown(f"- {tr(check.key)}")
    st.stop()

# ── Login page ─────────────────────────────────────────────────────────────
if not st.session_state["authenticated"]:
    render_login(
        logo_path=LOGO_PATH,
        translate=tr,
        authenticate=authenticate_user,
        establish_session=SESSION_CONTROLLER.establish,
        record_login=AUTH_STORE.record_login,
        remember_session=SESSION_CONTROLLER.remember,
    )


user: dict[str, Any] = st.session_state["user"]

render_sidebar(
    logo_path=LOGO_PATH,
    user=user,
    translate=tr,
    inference_health=inference_status,
    sign_out=SESSION_CONTROLLER.clear,
)


events = EVENT_STORE.list_for_user(user["email"], limit=2000)
page = st.session_state.get("page", "nav_home")
if page in {"nav_pipeline", "nav_resilience"} and user["role"] != "admin":
    page = "nav_home"
    st.session_state["page"] = page

# ── Accueil ──────────────────────────────────────────────────────────────────
if page == "nav_home":
    render_home(user, events, tr)

# ── Smail ─────────────────────────────────────────────────────────────────────
elif page == "nav_smail":
    render_smail(events, user["email"], tr, reclassify_event)


# ── Journal des menaces ───────────────────────────────────────────────────────
elif page == "nav_threat_log":
    render_threat_log(events, user["email"], tr, reclassify_event)

# ── Playground ────────────────────────────────────────────────────────────────
elif page == "nav_playground":
    render_playground(
        user_email=user["email"],
        scenarios=DEMO_EMAILS,
        translate=tr,
        classify=lambda subject, sender, text, use_llm=True, use_virustotal=True: (
            classify_email_for_ui(subject, sender, text, use_llm, use_virustotal)
        ),
        persist=lambda **evidence: EVENT_STORE.record(**evidence),
        render_result=lambda result: render_inference_result(result, tr),
    )

# ── Pipeline ───────────────────────────────────────────────────────────────────
elif page == "nav_pipeline":
    render_pipeline_page(
        user,
        tr,
        lambda title, operation: execute_pipeline_action(title, operation, tr, POC_SETTINGS),
    )


# ── Jeux de données ───────────────────────────────────────────────────────────
elif page == "nav_datasets":
    render_datasets(DATA_EVIDENCE_STORE, tr)

# ── Résilience contrôlée ─────────────────────────────────────────────────────
elif page == "nav_resilience":
    render_resilience(tr, inference_status, INFERENCE_CLIENT.run_fault_probe)

# ── Paramètres ────────────────────────────────────────────────────────────────
elif page == "nav_settings":
    runtime_ready, _ = inference_status()
    render_settings(
        user,
        tr,
        update_display_name,
        _set_lang,
        _set_theme,
        build_runtime_checks(
            POC_SETTINGS,
            POC_AUTH_DB_PATH,
            POC_DATA_DB_PATH,
            inference_ready=runtime_ready,
        ),
    )
