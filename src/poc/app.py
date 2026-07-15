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
from poc.presentation.result import render_inference_result
from poc.presentation.settings import render_settings
from poc.presentation.shell import render_login, render_sidebar
from poc.presentation.theme import initialize_theme, load_theme_css, set_theme
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
force_theme_css = ""
if theme_mode == "Light":
    force_theme_css = """
  :root {
    --bg: #F8FAFC !important;
    --surface: #FFFFFF !important;
    --border: #E2E8F0 !important;
    --border-line: #E2E8F0 !important;
    --text: #0F172A !important;
    --text-2: #475569 !important;
    --text-muted: #64748B !important;
    --cta-text: #06111F !important;
    --empty-text: #475569 !important;
    --primary: #4A90D9 !important;
    --primary-dark: #2E6BB5 !important;
    --primary-light: #EAF4FF !important;
    --primary-border: #C7E2FF !important;
    --accent: #F59E0B !important;
    --accent-dark: #B45309 !important;
    --danger: #D97706 !important;
    --danger-bg: #FFFBEB !important;
    --danger-border: #FDE68A !important;
    --nav-hover: #EEF3FF !important;
    --danger-semantic: #EF4444 !important;
    --safe-semantic: #047857 !important;
  }
  """
elif theme_mode == "Dark":
    force_theme_css = """
  :root {
    --bg: #07111F !important;
    --surface: #0B1626 !important;
    --border: #26364F !important;
    --border-line: rgba(255, 255, 255, 0.25) !important;
    --text: #F8FAFC !important;
    --text-2: #B7C4D7 !important;
    --text-muted: #8090A6 !important;
    --cta-text: #06111F !important;
    --empty-text: #F8FAFC !important;
    --primary: #4A90D9 !important;
    --primary-dark: #86C3F3 !important;
    --primary-light: #153F73 !important;
    --primary-border: #33445F !important;
    --accent: #F59E0B !important;
    --accent-dark: #B45309 !important;
    --danger: #F59E0B !important;
    --danger-bg: #451A03 !important;
    --danger-border: #78350F !important;
    --nav-hover: #1E3A5F !important;
    --danger-semantic: #EF4444 !important;
    --safe-semantic: #34D399 !important;
  }
  /* Forced dark: badge overrides */
  .badge-phishing { background: #450A0A !important; border-color: #7F1D1D !important; color: #F87171 !important; }
  .badge-safe, .badge-ok { background: #022C22 !important; border-color: #064E3B !important; color: #34D399 !important; }
  .badge-danger { background: #450A0A !important; border-color: #7F1D1D !important; color: #F87171 !important; }
  
  /* Forced dark: semantic buttons */
  div[data-testid="stElementContainer"]:has(.semantic-btn-danger) + div[data-testid="stElementContainer"] button { background-color: #450A0A !important; border-color: #7F1D1D !important; color: #F87171 !important; }
  div[data-testid="stElementContainer"]:has(.semantic-btn-danger) + div[data-testid="stElementContainer"] button:hover { background-color: #DC2626 !important; border-color: #DC2626 !important; color: #FFFFFF !important; }
  div[data-testid="stElementContainer"]:has(.semantic-btn-safe) + div[data-testid="stElementContainer"] button { background-color: #022C22 !important; border-color: #064E3B !important; color: #34D399 !important; }
  div[data-testid="stElementContainer"]:has(.semantic-btn-safe) + div[data-testid="stElementContainer"] button:hover { background-color: #059669 !important; border-color: #059669 !important; color: #FFFFFF !important; }
  
  /* Forced dark: CTA button text must follow theme tokens */
  button[data-testid^="stBaseButton-primary"],
  button[kind="primaryFormSubmit"],
  button[data-testid="stBaseButton-primaryFormSubmit"],
  button[data-testid^="stBaseButton-primary"] *,
  button[kind="primaryFormSubmit"] *,
  button[data-testid="stBaseButton-primaryFormSubmit"] *,
  .stButton > button[kind="primary"],
  .stButton > button[kind="primary"] *,
  div[data-testid="stFormSubmitButton"] button,
  div[data-testid="stFormSubmitButton"] button * { color: var(--cta-text) !important; }
  button[data-testid^="stBaseButton-primary"]:hover,
  button[data-testid^="stBaseButton-primary"]:focus,
  button[data-testid^="stBaseButton-primary"]:active,
  button[data-testid="stBaseButton-primaryFormSubmit"]:hover,
  button[data-testid="stBaseButton-primaryFormSubmit"]:focus,
  button[data-testid="stBaseButton-primaryFormSubmit"]:active,
  button[kind="primaryFormSubmit"]:hover,
  button[kind="primaryFormSubmit"]:focus,
  button[kind="primaryFormSubmit"]:active,
  .stButton > button[kind="primary"]:hover,
  .stButton > button[kind="primary"]:focus,
  .stButton > button[kind="primary"]:active,
  div[data-testid="stFormSubmitButton"] button:hover,
  div[data-testid="stFormSubmitButton"] button:focus,
  div[data-testid="stFormSubmitButton"] button:active,
  button[data-testid^="stBaseButton-primary"]:hover *,
  button[data-testid^="stBaseButton-primary"]:focus *,
  button[data-testid^="stBaseButton-primary"]:active *,
  button[data-testid="stBaseButton-primaryFormSubmit"]:hover *,
  button[data-testid="stBaseButton-primaryFormSubmit"]:focus *,
  button[data-testid="stBaseButton-primaryFormSubmit"]:active *,
  button[kind="primaryFormSubmit"]:hover *,
  button[kind="primaryFormSubmit"]:focus *,
  button[kind="primaryFormSubmit"]:active *,
  .stButton > button[kind="primary"]:hover *,
  .stButton > button[kind="primary"]:focus *,
  .stButton > button[kind="primary"]:active *,
  div[data-testid="stFormSubmitButton"] button:hover *,
  div[data-testid="stFormSubmitButton"] button:focus *,
  div[data-testid="stFormSubmitButton"] button:active * { color: var(--cta-text) !important; }

  /* Forced dark: login helper text must stay readable */
  [data-testid="InputInstructions"],
  [data-testid="InputInstructions"] *,
  [data-testid="InputInstructions"] span,
  [data-testid="InputInstructions"] span * {
    color: var(--empty-text) !important;
    opacity: 1 !important;
  }
  
  /* Forced dark: Active sidebar navigation button overrides */
  [data-testid="stSidebar"] button[data-testid^="stBaseButton-primary"] *,
  [data-testid="stSidebar"] button[kind="primary"] * {
    color: var(--text) !important;
  }
  [data-testid="stSidebar"] button[data-testid^="stBaseButton-primary"]:hover *,
  [data-testid="stSidebar"] button[data-testid^="stBaseButton-primary"]:focus *,
  [data-testid="stSidebar"] button[data-testid^="stBaseButton-primary"]:active *,
  [data-testid="stSidebar"] button[kind="primary"]:hover *,
  [data-testid="stSidebar"] button[kind="primary"]:focus *,
  [data-testid="stSidebar"] button[kind="primary"]:active * {
    color: var(--text) !important;
  }
  
  /* Forced dark: expander styling */
  [data-testid="stExpander"] {
    background: var(--surface) !important;
    border-color: var(--border) !important;
    color: var(--text) !important;
  }
  [data-testid="stExpander"] summary,
  [data-testid="stExpander"] summary * {
    color: var(--text-2) !important;
    background-color: transparent !important;
  }
  [data-testid="stExpander"] [data-testid="stExpanderDetails"],
  [data-testid="stExpander"] [data-testid="stExpanderDetails"] *,
  [data-testid="stExpander"] p,
  [data-testid="stExpander"] li,
  [data-testid="stExpander"] span {
    color: var(--text) !important;
    background-color: transparent !important;
  }
  [data-testid="stExpander"][open] summary,
  [data-testid="stExpander"][open] summary * {
    color: var(--text) !important;
  }
  
  /* Forced dark: collapsible sidebar button */
  [data-testid="stSidebarCollapseButton"] button svg { fill: #FFFFFF !important; color: #FFFFFF !important; }
  [data-testid="stSidebarCollapseButton"] button:hover svg { fill: var(--accent) !important; color: var(--accent) !important; }
  
  /* Forced dark: password reveal eye icon */
  [data-testid="stTextInput"] button svg,
  [data-testid="stPasswordInput"] button svg,
  button[kind="icon"] svg { fill: var(--text-2) !important; color: var(--text-2) !important; }
  [data-testid="stTextInput"] button:hover svg,
  [data-testid="stPasswordInput"] button:hover svg,
  button[kind="icon"]:hover svg { fill: var(--accent) !important; color: var(--accent) !important; }
  
  /* Forced dark: alert text contrast */
  div[data-testid="stAlert"],
  div[data-testid="stAlert"] *,
  div[data-testid="stNotification"],
  div[data-testid="stNotification"] *,
  .stAlert,
  .stAlert * { color: var(--text) !important; }
  """

st.set_page_config(
    page_title="Sicurre - POC",
    page_icon="S",
    layout="wide",
    initial_sidebar_state="expanded",
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
    return INFERENCE_CLIENT.health()


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
