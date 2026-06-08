from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import secrets
import sqlite3
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import bcrypt
import httpx
import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

try:
    from src.poc.local_runtime import (
        POC_AUTH_DB_PATH,
        POC_DATA_DB_PATH,
        build_poc_command_env,
        ensure_local_auth_db,
    )
except ModuleNotFoundError:
    from local_runtime import (  # type: ignore
        POC_AUTH_DB_PATH,
        POC_DATA_DB_PATH,
        build_poc_command_env,
        ensure_local_auth_db,
    )


ensure_local_auth_db()

ROOT_DIR = Path(__file__).resolve().parents[2]
I18N_PATH = ROOT_DIR / "src" / "poc" / "i18n.json"
LOGO_PATH = ROOT_DIR / "src" / "app" / "assets" / "sicurre.svg"

INFERENCE_URL = os.environ.get("POC_INFERENCE_URL", "http://127.0.0.1:8000/v1/classify")
INFERENCE_API_KEY = os.environ.get("INFERENCE_API_KEY", "")

st.set_page_config(
    page_title="Sicurre - POC Locale",
    page_icon="S",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
/* ── Light mode tokens ────────────────────────────────── */
:root {
  --bg: #F8FAFC;
  --surface: #FFFFFF;
  --border: #E2E8F0;
  --text: #0F2E7A;
  --text-2: #475569;
  --text-muted: #94A3B8;
  --primary: #1B4FCC;
  --primary-dark: #1239A6;
  --primary-light: #EEF3FF;
  --primary-border: #C7D7FF;
  --accent: #F59E0B;
  --accent-dark: #D97706;
  --danger: #EF4444;
  --danger-bg: #FEF2F2;
  --danger-border: #FECACA;
  --safe: #10B981;
  --safe-bg: #ECFDF5;
  --safe-border: #A7F3D0;
  --warning: #F59E0B;
  --warning-bg: #FFFBEB;
  --warning-border: #FDE68A;
  --nav-hover: #EEF3FF;
  --shadow: 0 1px 3px rgba(0,0,0,0.08);
}

/* ── Dark mode tokens (OS preference) ────────────────── */
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0F172A;
    --surface: #1E293B;
    --border: #334155;
    --text: #F1F5F9;
    --text-2: #94A3B8;
    --text-muted: #64748B;
    --primary: #60A5FA;
    --primary-dark: #3B82F6;
    --primary-light: #1E3A5F;
    --primary-border: #2D5A8E;
    --accent: #F59E0B;
    --accent-dark: #D97706;
    --danger: #F87171;
    --danger-bg: #450A0A;
    --danger-border: #7F1D1D;
    --safe: #34D399;
    --safe-bg: #022C22;
    --safe-border: #064E3B;
    --warning: #FBBF24;
    --warning-bg: #451A03;
    --warning-border: #78350F;
    --nav-hover: #1E3A5F;
    --shadow: 0 1px 3px rgba(0,0,0,0.4);
  }
}

/* ── Streamlit dark theme ──────────────────────────────── */
[data-theme="dark"] {
  --bg: #0F172A; --surface: #1E293B; --border: #334155;
  --text: #F1F5F9; --text-2: #94A3B8; --text-muted: #64748B;
  --primary: #60A5FA; --primary-dark: #3B82F6;
  --primary-light: #1E3A5F; --primary-border: #2D5A8E;
  --accent: #F59E0B; --accent-dark: #D97706;
  --danger: #F87171; --danger-bg: #450A0A; --danger-border: #7F1D1D;
  --safe: #34D399; --safe-bg: #022C22; --safe-border: #064E3B;
  --warning: #FBBF24; --warning-bg: #451A03; --warning-border: #78350F;
  --nav-hover: #1E3A5F; --shadow: 0 1px 3px rgba(0,0,0,0.4);
}

/* ── App shell ─────────────────────────────────────────── */
.stApp { background: var(--bg); }

[data-testid="stHeader"] {
  background: var(--surface) !important;
  border-bottom: 1px solid var(--border) !important;
}

[data-testid="stSidebar"] {
  background: var(--surface) !important;
  border-right: 1px solid var(--border) !important;
}

/* ── Hide chrome ───────────────────────────────────────── */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
[data-testid="stDeployButton"] { display: none; }

/* ── Logo background fix for dark mode clash ──────────── */
.logo-container {
  background: #FFFFFF;
  border-radius: 8px;
  padding: 10px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
}

/* ── Global action buttons (primary CTA) ──────────────── */
.stButton > button[kind="primary"] {
  background: var(--accent) !important;
  color: #fff !important;
  border: none !important;
  border-radius: 8px !important;
  font-weight: 600 !important;
}
.stButton > button[kind="primary"]:hover {
  background: var(--accent-dark) !important;
}

/* ── Secondary buttons ────────────────────────────────── */
.stButton > button[kind="secondary"] {
  border-radius: 8px !important;
  font-weight: 500 !important;
}

/* ── Forms ────────────────────────────────────────────── */
[data-testid="stForm"] {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
}

/* ── Checkboxes ───────────────────────────────────────── */
[data-baseweb="checkbox"] > div:first-child {
  /* Let's try to override Streamlit checkbox active state if possible. Streamlit 1.30+ uses complex divs. */
}
/* A simpler way to override checkbox color is using accent-color */
input[type="checkbox"] {
  accent-color: var(--primary) !important;
}

/* ── Sidebar nav buttons ───────────────────────────────── */
[data-testid="stSidebar"] .stButton {
  margin-bottom: 0.1rem !important;
}
[data-testid="stSidebar"] .stButton > button {
  background: transparent !important;
  border: none !important;
  border-radius: 6px !important;
  color: var(--text-2) !important;
  font-weight: 500 !important;
  font-size: 0.9rem !important;
  text-align: left !important;
  width: 100% !important;
  padding: 0.45rem 0.75rem !important;
  transition: background 0.12s ease !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
  background: var(--nav-hover) !important;
  color: var(--primary) !important;
}

.nav-active {
  display: block;
  padding: 0.45rem 0.75rem;
  background: var(--primary-light);
  border-left: 3px solid var(--primary);
  border-radius: 0 6px 6px 0;
  color: var(--primary);
  font-weight: 700;
  font-size: 0.9rem;
  margin-bottom: 0.5rem;
  margin-top: 0.2rem;
}

/* ── KPI cards ─────────────────────────────────────────── */
.kpi {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px 14px;
  box-shadow: var(--shadow);
}
.kpi .label {
  font-size: 0.72rem;
  font-weight: 700;
  color: var(--text-2);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 4px;
}
.kpi .value {
  font-size: 1.7rem;
  font-weight: 800;
  color: var(--text);
  line-height: 1;
}
.kpi .sub {
  font-size: 0.78rem;
  color: var(--text-muted);
  margin-top: 2px;
}

/* ── Verdict badges ────────────────────────────────────── */
.badge {
  display: inline-flex;
  align-items: center;
  padding: 0.2rem 0.65rem;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 700;
  white-space: nowrap;
}
.badge-phishing { background: var(--danger-bg); border: 1px solid var(--danger-border); color: var(--danger); }
.badge-spam     { background: var(--warning-bg); border: 1px solid var(--warning-border); color: var(--warning); }
.badge-safe     { background: var(--safe-bg); border: 1px solid var(--safe-border); color: var(--safe); }
/* Legacy aliases */
.badge-ok      { background: var(--safe-bg); border: 1px solid var(--safe-border); color: var(--safe); }
.badge-danger  { background: var(--danger-bg); border: 1px solid var(--danger-border); color: var(--danger); }
.badge-warn    { background: var(--warning-bg); border: 1px solid var(--warning-border); color: var(--warning); }

/* ── Email card (Smail) ────────────────────────────────── */
.email-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 6px;
}
.email-card:hover { border-color: var(--primary); }
.email-card .ec-sender { font-size: 0.78rem; color: var(--text-2); margin-bottom: 1px; }
.email-card .ec-subject { font-size: 0.95rem; font-weight: 700; color: var(--text); }
.email-card .ec-snippet { font-size: 0.82rem; color: var(--text-muted); margin-top: 3px; }

/* ── Result card (Playground) ──────────────────────────── */
.result-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px;
  box-shadow: var(--shadow);
}
.result-phishing { border-top: 4px solid var(--danger); }
.result-spam     { border-top: 4px solid var(--warning); }
.result-safe     { border-top: 4px solid var(--safe); }

/* ── Threat log cards ──────────────────────────────────── */
.threat-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-left: 4px solid var(--danger);
  border-radius: 0 10px 10px 0;
  padding: 12px 14px;
  margin-bottom: 6px;
}
.threat-card .tc-subject { font-size: 0.95rem; font-weight: 700; color: var(--text); }
.threat-card .tc-meta { font-size: 0.78rem; color: var(--text-2); }

/* ── Generic content card ──────────────────────────────── */
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px 16px;
  margin-bottom: 8px;
  box-shadow: var(--shadow);
}
.card p { margin: 0; }

/* ── Login form ────────────────────────────────────────── */
.login-wrap {
  max-width: 420px;
  margin: 3.5rem auto 0 auto;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 1.8rem 2rem;
  box-shadow: 0 4px 24px rgba(0,0,0,0.06);
  text-align: center;
}

/* ── Misc ──────────────────────────────────────────────── */
.small { font-size: 0.84rem; color: var(--text-2); }
.muted { font-size: 0.78rem; color: var(--text-muted); }
.block {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px 16px;
}
.status-dot {
  display: inline-block;
  width: 8px; height: 8px;
  border-radius: 50%;
  vertical-align: middle;
  margin-right: 4px;
}
.dot-green { background: var(--safe); }
.dot-red   { background: var(--danger); }
.dot-grey  { background: var(--text-muted); }
</style>
""",
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


def _load_i18n() -> dict[str, dict[str, str]]:
    if I18N_PATH.exists():
        return json.loads(I18N_PATH.read_text(encoding="utf-8"))
    return {
        "fr": {"title": "Sicurre"},
        "en": {"title": "Sicurre"},
    }


def _init_lang() -> None:
    if "lang" not in st.session_state:
        qp_lang = st.query_params.get("lang", "fr")
        if isinstance(qp_lang, list):
            qp_lang = qp_lang[0] if qp_lang else "fr"
        st.session_state["lang"] = "en" if str(qp_lang).lower() == "en" else "fr"


_I18N = _load_i18n()
_init_lang()


def tr(key: str) -> str:
    lang = st.session_state.get("lang", "fr")
    return _I18N.get(lang, {}).get(key, _I18N.get("fr", {}).get(key, key))


def _set_lang(lang: str) -> None:
    st.session_state["lang"] = lang
    st.query_params["lang"] = lang


def _auth_q(query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    conn = sqlite3.connect(str(POC_AUTH_DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(query, params)
        return cur.fetchall()
    finally:
        conn.close()


def _auth_exec(query: str, params: tuple[Any, ...] = ()) -> None:
    conn = sqlite3.connect(str(POC_AUTH_DB_PATH))
    try:
        conn.execute(query, params)
        conn.commit()
    finally:
        conn.close()


@st.cache_resource
def _data_engine():
    return create_engine(f"sqlite:///{POC_DATA_DB_PATH}", future=True)


def _data_q(query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    retries = 4
    wait_s = 0.2
    for attempt in range(retries):
        try:
            with _data_engine().connect() as conn:
                conn.execute(text("PRAGMA journal_mode=WAL"))
                result = conn.execute(text(query), params or {})
                return [dict(row._mapping) for row in result]
        except OperationalError as exc:
            if "database is locked" in str(exc).lower() and attempt < retries - 1:
                time.sleep(wait_s * (2**attempt))
                continue
            if "no such table" in str(exc).lower():
                return []
            raise
    return []


def _data_table_exists(table_name: str) -> bool:
    conn = sqlite3.connect(str(POC_DATA_DB_PATH))
    try:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            (table_name,),
        ).fetchone()
        return bool(row)
    finally:
        conn.close()


def _fmt_num(value: int | float) -> str:
    if isinstance(value, float):
        return f"{value:,.2f}".replace(",", " ")
    return f"{value:,}".replace(",", " ")


def _safe_text(value: str, max_len: int = 200) -> str:
    clean = " ".join((value or "").split())
    return clean if len(clean) <= max_len else f"{clean[:max_len - 1]}..."


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _eff_verdict(event: dict[str, Any]) -> str:
    """Effective safety verdict, considering user override."""
    return str(event.get("override_verdict") or event.get("safety_verdict", "safe"))


def _eff_label(event: dict[str, Any]) -> str:
    """Original label verdict (class from classifier)."""
    return str(event.get("label_verdict", "legitimate"))


def _delink(text: str) -> str:
    """Replace URLs with a safe placeholder."""
    return re.sub(r"https?://\S+", "[LIEN DÉSACTIVÉ]", text)


def _set_user_session(user: dict[str, Any]) -> None:
    st.session_state["authenticated"] = True
    st.session_state["user"] = {
        "id": user["id"],
        "email": user["email"],
        "display_name": user["display_name"],
        "role": user["role"],
    }


def _persist_session(user_id: str) -> str:
    sid = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    _auth_exec(
        "UPDATE poc_user SET session_token_hash = ?, session_expires_at = ? WHERE id = ?",
        (_hash_token(sid), expires_at, user_id),
    )
    return sid


def _restore_session_from_query() -> None:
    if st.session_state.get("authenticated"):
        return

    sid = st.query_params.get("sid")
    if isinstance(sid, list):
        sid = sid[0] if sid else ""
    if not sid:
        return

    if rows := _auth_q(
        """
        SELECT *
        FROM poc_user
        WHERE session_token_hash = ?
          AND session_expires_at IS NOT NULL
          AND session_expires_at > ?
        LIMIT 1
        """,
        (_hash_token(str(sid)), datetime.now(timezone.utc).isoformat()),
    ):
        _set_user_session(dict(rows[0]))


def _clear_session() -> None:
    if user := st.session_state.get("user"):
        _auth_exec(
            "UPDATE poc_user SET session_token_hash = NULL, session_expires_at = NULL WHERE id = ?",
            (user["id"],),
        )
    for key in [
        "authenticated",
        "user",
        "show_login",
        "last_result",
        "smail_inbox",
        "smail_blocked",
    ]:
        st.session_state.pop(key, None)
    if "sid" in st.query_params:
        del st.query_params["sid"]


def check_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"), hashed_password.encode("utf-8")
        )
    except Exception:
        return False


def authenticate_user(email: str, password: str) -> dict[str, Any] | None:
    rows = _auth_q("SELECT * FROM poc_user WHERE email = ?", (email.strip().lower(),))
    if not rows:
        return None

    user = dict(rows[0])
    return user if check_password(password, user["password_hash"]) else None


def inference_status() -> tuple[bool, str]:
    if not INFERENCE_API_KEY:
        return False, "INFERENCE_API_KEY missing"

    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(
                INFERENCE_URL.replace("/v1/classify", "/health"),
                headers={"Authorization": f"Bearer {INFERENCE_API_KEY}"},
            )
        if response.status_code == 200:
            return True, tr("inference_up")
        return False, f"HTTP {response.status_code}"
    except Exception as exc:
        return False, f"{tr('inference_down')}: {exc}"


def normalize_inference_result(raw: dict[str, Any]) -> dict[str, Any]:
    verdict = str(raw.get("verdict") or "safe").lower()
    is_phishing = bool(raw.get("is_phishing", verdict == "phishing"))
    label_verdict = raw.get("label_verdict") or (raw.get("stage_labels") or {}).get(
        "onnx"
    )
    label_verdict = str(
        label_verdict or ("phishing" if is_phishing else "legitimate")
    ).lower()

    return {
        "safety_verdict": "phishing" if is_phishing else "safe",
        "label_verdict": label_verdict,
        "is_phishing": is_phishing,
        "composite_score": float(raw.get("composite_score") or 0.0),
        "llm_provider": str(raw.get("llm_provider") or "n/a"),
        "explanation": str(raw.get("explanation") or tr("no_explanation")),
        "stage_scores": raw.get("stage_scores") or {},
        "stage_labels": raw.get("stage_labels") or {},
        "label_distribution": raw.get("label_distribution") or {},
        "stage_breakdown": raw.get("stage_breakdown") or {},
        "raw": raw,
    }


def simulated_result(subject: str, sender: str, text_value: str) -> dict[str, Any]:
    full = f"{subject} {sender} {text_value}".lower()
    phishing_terms = [
        "urgent",
        "mot de passe",
        "rib",
        "suspendu",
        "verifier",
        "confirmez",
    ]
    spam_terms = ["promo", "offre", "gratuit", "bonus", "remise", "leads"]

    phishing_hits = sum(term in full for term in phishing_terms)
    spam_hits = sum(term in full for term in spam_terms)

    if phishing_hits >= 2:
        raw = {
            "verdict": "phishing",
            "label_verdict": "phishing",
            "is_phishing": True,
            "composite_score": 0.78,
            "stage_scores": {"onnx": 0.71, "llm": 0.82},
            "stage_labels": {"onnx": "phishing", "llm": "phishing"},
            "label_distribution": {"legitimate": 0.04, "spam": 0.18, "phishing": 0.78},
            "explanation": "Simulation locale: tentative de phishing probable.",
            "llm_provider": "simulation",
        }
    elif spam_hits >= 2:
        raw = {
            "verdict": "safe",
            "label_verdict": "spam",
            "is_phishing": False,
            "composite_score": 0.28,
            "stage_scores": {"onnx": 0.19, "llm": 0.33},
            "stage_labels": {"onnx": "spam", "llm": "spam"},
            "label_distribution": {"legitimate": 0.18, "spam": 0.72, "phishing": 0.10},
            "explanation": "Simulation locale: contenu promotionnel detecte.",
            "llm_provider": "simulation",
        }
    else:
        raw = {
            "verdict": "safe",
            "label_verdict": "legitimate",
            "is_phishing": False,
            "composite_score": 0.08,
            "stage_scores": {"onnx": 0.06, "llm": 0.09},
            "stage_labels": {"onnx": "legitimate", "llm": "legitimate"},
            "label_distribution": {"legitimate": 0.86, "spam": 0.09, "phishing": 0.05},
            "explanation": "Simulation locale: email legitime.",
            "llm_provider": "simulation",
        }

    return normalize_inference_result(raw)


def classify_email(
    subject: str,
    sender: str,
    text_value: str,
    use_llm: bool = True,
    use_virustotal: bool = True,
) -> dict[str, Any]:
    payload = {
        "subject": subject,
        "sender": sender,
        "text": text_value,
        "use_llm": use_llm,
        "use_virustotal": use_virustotal,
    }
    started = time.perf_counter()

    try:
        with httpx.Client(timeout=35.0) as client:
            response = client.post(
                INFERENCE_URL,
                json=payload,
                headers={"Authorization": f"Bearer {INFERENCE_API_KEY}"},
            )
        response.raise_for_status()
        normalized = normalize_inference_result(response.json())
        normalized["source"] = "api"
    except Exception as exc:
        st.warning(f"{tr('api_fallback')}: {exc}")
        normalized = simulated_result(subject, sender, text_value)
        normalized["source"] = "simulation"

    normalized["params"] = {"use_llm": use_llm, "use_virustotal": use_virustotal}
    normalized["latency_ms"] = round((time.perf_counter() - started) * 1000.0, 2)
    return normalized


def log_inference_event(
    *,
    user_email: str,
    context: str,
    subject: str,
    sender: str,
    text_value: str,
    result: dict[str, Any],
    delivered_in_smail: bool,
    expected_label: str | None,
) -> None:
    params = result.get("params") or {}
    _auth_exec(
        """
        INSERT INTO poc_inference_event (
            id,
            created_at,
            user_email,
            context,
            subject,
            sender,
            snippet,
            safety_verdict,
            label_verdict,
            composite_score,
            is_phishing,
            delivered_in_smail,
            llm_provider,
            explanation,
            latency_ms,
            used_llm,
            used_virustotal,
            inference_source,
            stage_scores_json,
            stage_labels_json,
            stage_breakdown_json,
            expected_label
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid4()),
            datetime.now(timezone.utc).isoformat(),
            user_email,
            context,
            subject,
            sender,
            _safe_text(text_value, 240),
            result["safety_verdict"],
            result["label_verdict"],
            result["composite_score"],
            1 if result["is_phishing"] else 0,
            1 if delivered_in_smail else 0,
            result.get("llm_provider", "n/a"),
            result.get("explanation", ""),
            float(result.get("latency_ms") or 0.0),
            1 if params.get("use_llm") else 0,
            1 if params.get("use_virustotal") else 0,
            str(result.get("source") or "api"),
            json.dumps(result.get("stage_scores") or {}, ensure_ascii=True),
            json.dumps(result.get("stage_labels") or {}, ensure_ascii=True),
            json.dumps(result.get("stage_breakdown") or {}, ensure_ascii=True),
            expected_label,
        ),
    )


def reclassify_event(event_id: str, new_verdict: str, by_user: str) -> None:
    """Override the safety verdict for a single event."""
    _auth_exec(
        "UPDATE poc_inference_event SET override_verdict = ?, override_by = ?, overridden_at = ? WHERE id = ?",
        (new_verdict, by_user, datetime.now(timezone.utc).isoformat(), event_id),
    )


def get_events(limit: int = 500) -> list[dict[str, Any]]:
    rows = _auth_q(
        """
        SELECT
            id,
            created_at,
            user_email,
            context,
            subject,
            sender,
            snippet,
            safety_verdict,
            label_verdict,
            composite_score,
            is_phishing,
            delivered_in_smail,
            llm_provider,
            explanation,
            latency_ms,
            used_llm,
            used_virustotal,
            inference_source,
            stage_scores_json,
            stage_labels_json,
            stage_breakdown_json,
            expected_label,
            override_verdict,
            override_by,
            overridden_at
        FROM poc_inference_event
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (limit,),
    )

    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["stage_scores"] = json.loads(item.pop("stage_scores_json") or "{}")
        item["stage_labels"] = json.loads(item.pop("stage_labels_json") or "{}")
        item["stage_breakdown"] = json.loads(item.pop("stage_breakdown_json") or "{}")
        item["is_phishing"] = bool(item["is_phishing"])
        item["delivered_in_smail"] = bool(item["delivered_in_smail"])
        item["used_llm"] = bool(item["used_llm"])
        item["used_virustotal"] = bool(item["used_virustotal"])
        out.append(item)
    return out


def run_and_stream(command: str) -> tuple[bool, str]:
    process = subprocess.Popen(
        ["bash", "-lc", command],
        cwd=ROOT_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=build_poc_command_env(),
    )

    output_lines: list[str] = []
    with st.status(tr("pipeline_running"), expanded=True) as status:
        placeholder = st.empty()
        while process.poll() is None:
            line = process.stdout.readline() if process.stdout else ""
            if line:
                output_lines.append(line)
                placeholder.code("".join(output_lines[-40:]), language="bash")
        tail = process.stdout.read() if process.stdout else ""
        if tail:
            output_lines.append(tail)
            placeholder.code("".join(output_lines[-40:]), language="bash")

        code = process.returncode
        if code == 0:
            status.update(label=tr("pipeline_done"), state="complete")
            return True, "".join(output_lines)
        status.update(label=f"{tr('pipeline_failed')} ({code})", state="error")
        return False, "".join(output_lines)


def run_pipeline_action(title: str, command: str) -> None:
    if st.session_state.get("pipeline_busy", False):
        st.warning(tr("pipeline_busy"))
        return

    st.session_state["pipeline_busy"] = True
    try:
        with st.spinner(f"{title}..."):
            ok, output = run_and_stream(command)
        st.session_state["last_pipeline_output"] = output
        st.session_state["last_pipeline_success"] = ok
    finally:
        st.session_state["pipeline_busy"] = False


def render_logo_html(width: int = 160, center: bool = False) -> None:
    if LOGO_PATH.exists():
        b64 = base64.b64encode(LOGO_PATH.read_bytes()).decode()
        align = "margin: 0 auto;" if center else ""
        display = "display: block;" if center else "display: inline-block;"
        st.markdown(
            f'<div class="logo-container" style="{display}{align}">'
            f'<img src="data:image/svg+xml;base64,{b64}" width="{width}" />'
            f"</div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            "<span style='font-size:1.4rem;font-weight:900;letter-spacing:-1px;'"
            ">SICURRE</span>",
            unsafe_allow_html=True,
        )


def render_bar_chart(
    rows: list[dict[str, Any]], x_field: str, y_field: str, title: str
) -> None:
    if not rows:
        st.info(tr("no_data"))
        return
    chart_spec = {
        "mark": {"type": "bar", "cornerRadiusTopLeft": 3, "cornerRadiusTopRight": 3},
        "encoding": {
            "x": {"field": x_field, "type": "nominal", "axis": {"labelAngle": 0}},
            "y": {"field": y_field, "type": "quantitative"},
            "color": {"value": "#1B4FCC"},
        },
        "config": {"background": "transparent", "view": {"stroke": "transparent"}},
    }
    st.markdown(f"#### {title}")
    st.vega_lite_chart(rows, chart_spec, width="stretch")


def render_class_dist_chart(events: list[dict[str, Any]]) -> None:
    """Horizontal bar chart with per-class brand colors."""
    fr_labels = {
        "legitimate": tr("class_legitimate"),
        "spam": tr("class_spam"),
        "phishing": tr("class_phishing"),
    }
    counts = {k: 0 for k in fr_labels}
    for e in events:
        lv = _eff_label(e) if _eff_verdict(e) != "phishing" else "phishing"
        if lv in counts:
            counts[lv] += 1
    rows = [
        {"classe": fr_labels[k], "count": v, "_key": k}
        for k, v in counts.items()
        if v > 0
    ]
    if not rows:
        st.info(tr("no_data"))
        return
    spec = {
        "mark": {
            "type": "bar",
            "cornerRadiusTopRight": 4,
            "cornerRadiusBottomRight": 4,
        },
        "encoding": {
            "y": {
                "field": "classe",
                "type": "nominal",
                "sort": "-x",
                "axis": {"title": None, "labelFontSize": 12},
            },
            "x": {
                "field": "count",
                "type": "quantitative",
                "axis": {"title": "Nombre", "grid": False},
            },
            "color": {
                "field": "_key",
                "type": "nominal",
                "scale": {
                    "domain": ["legitimate", "spam", "phishing"],
                    "range": ["#10B981", "#F59E0B", "#EF4444"],
                },
                "legend": None,
            },
        },
        "config": {"background": "transparent", "view": {"stroke": "transparent"}},
    }
    st.vega_lite_chart(rows, spec, width="stretch")


def _conf_bar(label: str, pct: float, color: str) -> str:
    w = min(max(pct, 0.0), 100.0)
    return (
        f"<div style='margin-bottom:8px;'>"
        f"<div style='display:flex;justify-content:space-between;margin-bottom:2px;'>"
        f"<span style='font-size:0.82rem;color:var(--text-2);'>{label}</span>"
        f"<span style='font-size:0.82rem;font-weight:700;color:{color};'>{pct:.0f} %</span>"
        f"</div>"
        f"<div style='height:6px;border-radius:3px;background:var(--border);overflow:hidden;'>"
        f"<div style='width:{w}%;height:100%;background:{color};border-radius:3px;'></div>"
        f"</div></div>"
    )


def render_result_card(result: dict[str, Any]) -> None:
    safety = result["safety_verdict"]
    label = result["label_verdict"]
    score_pct = float(result["composite_score"]) * 100.0
    lat = float(result.get("latency_ms") or 0.0)
    explanation = result.get("explanation") or tr("no_explanation")

    # Verdict class
    if safety == "phishing":
        card_cls = "result-phishing"
        badge_cls = "badge-phishing"
        verdict_text = tr("class_phishing")
    elif label == "spam":
        card_cls = "result-spam"
        badge_cls = "badge-spam"
        verdict_text = tr("class_spam")
    else:
        card_cls = "result-safe"
        badge_cls = "badge-safe"
        verdict_text = tr("class_legitimate")

    # Label distribution bars
    dist = result.get("label_distribution") or {}
    class_colors = {"phishing": "#EF4444", "spam": "#F59E0B", "legitimate": "#10B981"}
    class_labels = {
        "phishing": tr("class_phishing"),
        "spam": tr("class_spam"),
        "legitimate": tr("class_legitimate"),
    }
    bars_html = ""
    for cls in ["phishing", "spam", "legitimate"]:
        if cls in dist:
            bars_html += _conf_bar(
                class_labels[cls],
                float(dist[cls]) * 100.0,
                class_colors[cls],
            )

    st.markdown(
        f"""
<div class='result-card {card_cls}'>
  <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;'>
    <span class='badge {badge_cls}'>{verdict_text}</span>
    <span style='font-size:0.8rem;color:var(--text-muted);'>Score {score_pct:.1f} % | {lat:.0f} ms</span>
  </div>
  <div style='margin-bottom:12px;'>
    <div style='font-size:0.78rem;color:var(--text-2);margin-bottom:4px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;'>{tr('explanation')}</div>
    <p style='font-size:0.9rem;color:var(--text);margin:0;'>{explanation}</p>
  </div>
  <div style='font-size:0.78rem;color:var(--text-2);margin-bottom:6px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;'>{tr('class_distribution')}</div>
  {bars_html}
</div>
""",
        unsafe_allow_html=True,
    )

    if result.get("stage_breakdown"):
        with st.expander(tr("stage_scores"), expanded=False):
            st.json(result["stage_breakdown"])


if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "show_login" not in st.session_state:
    st.session_state["show_login"] = True
if "last_result" not in st.session_state:
    st.session_state["last_result"] = None
if "page" not in st.session_state:
    st.session_state["page"] = "nav_home"

_restore_session_from_query()

# ── Login page ─────────────────────────────────────────────────────────────
if not st.session_state["authenticated"]:
    # Language selector — top right
    lang_top_c1, lang_top_c2 = st.columns([5, 1])
    with lang_top_c2:
        lopt = st.selectbox(
            "",
            options=[("fr", "FR"), ("en", "EN")],
            index=0 if st.session_state.get("lang", "fr") == "fr" else 1,
            format_func=lambda item: item[1],
            key="login_lang_selector",
            label_visibility="collapsed",
        )
        if lopt[0] != st.session_state.get("lang"):
            _set_lang(lopt[0])
            st.rerun()

    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c2:
        st.markdown("<div style='margin-top: 2.5rem;'></div>", unsafe_allow_html=True)
        render_logo_html(width=120, center=True)
        st.markdown("<br/>", unsafe_allow_html=True)
        st.markdown(
            f"<h3 style='margin:0 0 4px;color:var(--text);text-align:center;'>{tr('login_title')}</h3>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<p style='font-size:0.88rem;color:var(--text-2);margin-bottom:1.2rem;text-align:center;'>{tr('login_subtitle')}</p>",
            unsafe_allow_html=True,
        )

        with st.form("login_form"):
            email = st.text_input(tr("email"), placeholder="you@company.com")
            password = st.text_input(tr("password"), type="password")
            remember = st.checkbox(tr("remember_me"), value=True)
            submitted = st.form_submit_button(
                tr("sign_in"), type="primary", use_container_width=True
            )

        if submitted:
            user = authenticate_user(email, password)
            if user:
                _set_user_session(user)
                _auth_exec(
                    "UPDATE poc_user SET last_login_at = ? WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(), user["id"]),
                )
                if remember:
                    sid = _persist_session(user["id"])
                    st.query_params["sid"] = sid
                st.rerun()
            else:
                st.warning("⚠️ " + tr("invalid_credentials"))

        st.markdown("</div>", unsafe_allow_html=True)
    st.stop()


user = st.session_state["user"]

# ── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    render_logo_html(width=100)
    st.markdown("<div style='margin-bottom:12px;'></div>", unsafe_allow_html=True)
    st.markdown(
        f"<div style='font-size:0.82rem;color:var(--text-2);margin-bottom:0;'>{tr('welcome')}</div>"
        f"<div style='font-weight:700;font-size:0.97rem;color:var(--text);margin-bottom:12px;'>"
        f"{user['display_name']}</div>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    NAV_KEYS = [
        "nav_home",
        "nav_smail",
        "nav_threat_log",
        "nav_playground",
        "nav_pipeline",
        "nav_datasets",
        "nav_settings",
    ]
    current_page = st.session_state.get("page", "nav_home")
    for nav_key in NAV_KEYS:
        if nav_key == current_page:
            st.markdown(
                f"<div class='nav-active'>{tr(nav_key)}</div>",
                unsafe_allow_html=True,
            )
        else:
            if st.button(tr(nav_key), key=f"_nav_{nav_key}"):
                st.session_state["page"] = nav_key
                st.rerun()

    st.markdown("---")

    # Inference status at bottom
    ok, status_text = inference_status()
    dot_cls = "dot-green" if ok else "dot-red"
    st.markdown(
        f"<span class='status-dot {dot_cls}'></span>"
        f"<span style='font-size:0.8rem;color:var(--text-2);'>{tr('inference_status')}</span>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<span style='font-size:0.75rem;color:var(--text-muted);'>{status_text}</span>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-top:12px;'></div>", unsafe_allow_html=True)

    if st.button(tr("sign_out"), key="_sidebar_signout"):
        _clear_session()
        st.rerun()


events = get_events(limit=2000)
page = st.session_state.get("page", "nav_home")

# ── Accueil ──────────────────────────────────────────────────────────────────
if page == "nav_home":
    st.markdown(
        f"<h1 style='margin-bottom:4px;'>{tr('welcome')}, {user['display_name']}</h1>",
        unsafe_allow_html=True,
    )
    st.caption(tr("home_subtitle"))
    st.markdown("<div style='margin-bottom:4px;'></div>", unsafe_allow_html=True)

    total = len(events)
    blocked = sum(1 for e in events if _eff_verdict(e) == "phishing")
    delivered = sum(1 for e in events if _eff_verdict(e) == "safe")
    spam_safe = sum(
        1 for e in events if _eff_verdict(e) == "safe" and _eff_label(e) == "spam"
    )

    if eval_events := [e for e in events if e.get("expected_label")]:
        fp_block = sum(
            1
            for e in eval_events
            if _eff_verdict(e) == "phishing" and e.get("expected_label") != "phishing"
        )
        fn_miss = sum(
            1
            for e in eval_events
            if _eff_verdict(e) != "phishing" and e.get("expected_label") == "phishing"
        )
        label_acc = (
            sum(1 for e in eval_events if _eff_label(e) == e["expected_label"])
            / len(eval_events)
            * 100.0
        )
    else:
        fp_block = 0
        fn_miss = 0
        label_acc = 0.0

    latencies = [
        float(e.get("latency_ms") or 0.0)
        for e in events
        if float(e.get("latency_ms") or 0.0) > 0
    ]
    p95 = (
        sorted(latencies)[max(int(len(latencies) * 0.95) - 1, 0)] if latencies else 0.0
    )

    r1, r2, r3, r4 = st.columns(4)
    r1.markdown(
        f"<div class='kpi'><div class='label'>{tr('emails_scanned')}</div>"
        f"<div class='value'>{_fmt_num(total)}</div></div>",
        unsafe_allow_html=True,
    )
    r2.markdown(
        f"<div class='kpi'><div class='label'>{tr('phishing_blocked')}</div>"
        f"<div class='value' style='color:var(--danger);'>{_fmt_num(blocked)}</div></div>",
        unsafe_allow_html=True,
    )
    r3.markdown(
        f"<div class='kpi'><div class='label'>{tr('delivered_inbox')}</div>"
        f"<div class='value' style='color:var(--safe);'>{_fmt_num(delivered)}</div></div>",
        unsafe_allow_html=True,
    )
    r4.markdown(
        f"<div class='kpi'><div class='label'>{tr('safe_spam')}</div>"
        f"<div class='value' style='color:var(--warning);'>{_fmt_num(spam_safe)}</div></div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-bottom:8px;'></div>", unsafe_allow_html=True)

    r5, r6, r7, r8 = st.columns(4)
    r5.markdown(
        f"<div class='kpi'><div class='label'>{tr('label_accuracy')}</div>"
        f"<div class='value'>{label_acc:.1f}%</div></div>",
        unsafe_allow_html=True,
    )
    r6.markdown(
        f"<div class='kpi'><div class='label'>{tr('false_positive')}</div>"
        f"<div class='value'>{fp_block}</div></div>",
        unsafe_allow_html=True,
    )
    r7.markdown(
        f"<div class='kpi'><div class='label'>{tr('false_negative')}</div>"
        f"<div class='value'>{fn_miss}</div></div>",
        unsafe_allow_html=True,
    )
    r8.markdown(
        f"<div class='kpi'><div class='label'>{tr('latency_p95')}</div>"
        f"<div class='value'>{p95:.0f} ms</div></div>",
        unsafe_allow_html=True,
    )

    st.markdown("<div style='margin-bottom:16px;'></div>", unsafe_allow_html=True)

    st.markdown(f"#### {tr('recent_activity')}")
    if not events:
        st.info(tr("no_events"))
    else:
        for event in events[:6]:
            ev = _eff_verdict(event)
            el = _eff_label(event)
            if ev == "phishing":
                badge = (
                    f"<span class='badge badge-phishing'>{tr('class_phishing')}</span>"
                )
            elif el == "spam":
                badge = f"<span class='badge badge-spam'>{tr('class_spam')}</span>"
            else:
                badge = (
                    f"<span class='badge badge-safe'>{tr('class_legitimate')}</span>"
                )
            ts = event["created_at"].replace("T", " ")[:16]
            st.markdown(
                f"<div class='card' style='padding:10px 12px;margin-bottom:5px;'>"
                f"<div style='font-size:0.9rem;font-weight:600;color:var(--text);'>"
                f"{_safe_text(event['subject'], 60)}</div>"
                f"<div style='font-size:0.78rem;color:var(--text-2);margin-top:3px;'>"
                f"{_safe_text(event['sender'], 50)} &middot; {ts} &middot; {badge}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

# ── Smail ─────────────────────────────────────────────────────────────────────
elif page == "nav_smail":
    st.title(tr("smail_title"))
    st.caption(tr("smail_inbox_subtitle"))

    # Fetch safe events from playground/manual/smail context using effective verdict
    safe_events = [
        e
        for e in events
        if _eff_verdict(e) == "safe"
        and e.get("context") in ("playground", "manual", "smail")
    ]
    legit_events = [e for e in safe_events if _eff_label(e) == "legitimate"]
    spam_events = [e for e in safe_events if _eff_label(e) == "spam"]

    tab1, tab2 = st.tabs(
        [
            f"{tr('smail_inbox_tab')} ({len(legit_events)})",
            f"{tr('smail_spam_tab')} ({len(spam_events)})",
        ]
    )

    def _smail_card(ev: dict[str, Any], tab_key: str) -> None:
        ts = ev["created_at"].replace("T", " ")[:16]
        corrected = bool(ev.get("override_verdict"))
        corr_note = (
            f"<span style='font-size:0.74rem;color:var(--text-muted);'> ({tr('corrected_label')})</span>"
            if corrected
            else ""
        )
        snip = _delink(_safe_text(ev.get("snippet") or "", 160))
        st.markdown(
            f"<div class='email-card'>"
            f"<div class='ec-sender'>{_safe_text(ev['sender'], 70)} &middot; {ts}{corr_note}</div>"
            f"<div class='ec-subject'>{_safe_text(ev['subject'], 80)}</div>"
            f"<div class='ec-snippet'>{snip}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        if st.button(
            tr("flag_false_negative"),
            key=f"fn_{tab_key}_{ev['id']}",
        ):
            reclassify_event(ev["id"], "phishing", user["email"])
            st.toast(tr("reclassified_done"), icon="✅")
            st.rerun()

    with tab1:
        if not legit_events:
            st.info(tr("smail_empty_inbox"))
        else:
            for ev in legit_events:
                _smail_card(ev, "inbox")

    with tab2:
        if not spam_events:
            st.info(tr("smail_empty_spam"))
        else:
            for ev in spam_events:
                _smail_card(ev, "spam")


# ── Journal des menaces ───────────────────────────────────────────────────────
elif page == "nav_threat_log":
    st.title(tr("threat_title"))
    st.caption(tr("threat_reclassify_subtitle"))

    # Period filter
    c1, c2, c3 = st.columns([1, 2, 2])
    with c1:
        period_opts = [tr("period_all"), tr("period_today"), tr("period_week")]
        period_sel = st.selectbox(
            tr("filter_period"), period_opts, label_visibility="collapsed"
        )

    now_utc = datetime.now(timezone.utc)
    phishing_events = [e for e in events if _eff_verdict(e) == "phishing"]

    if period_sel == tr("period_today"):
        cutoff = (now_utc - timedelta(days=1)).isoformat()
        phishing_events = [e for e in phishing_events if e["created_at"] >= cutoff]
    elif period_sel == tr("period_week"):
        cutoff = (now_utc - timedelta(days=7)).isoformat()
        phishing_events = [e for e in phishing_events if e["created_at"] >= cutoff]

    if not phishing_events:
        st.info(tr("no_events"))
    else:
        for event in phishing_events[:80]:
            ts = event["created_at"].replace("T", " ")[:16]
            score_pct = float(event.get("composite_score") or 0.0) * 100.0
            corr_note = ""
            if event.get("override_verdict"):
                corr_note = f" &nbsp;<span class='badge badge-safe'>{tr('corrected_label')}</span>"
            snip = _delink(_safe_text(event.get("snippet") or "", 200))
            st.markdown(
                f"<div class='threat-card'>"
                f"<div class='tc-subject'>{_safe_text(event['subject'], 90)}</div>"
                f"<div class='tc-meta'>{_safe_text(event['sender'], 70)} &middot; {ts} &middot; {score_pct:.0f}\u202f%{corr_note}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
            with st.expander(tr("expand_body"), expanded=False):
                st.markdown(
                    f"<p style='font-size:0.9rem;color:var(--text);'>{snip}</p>",
                    unsafe_allow_html=True,
                )
                if st.button(tr("reclassify_safe"), key=f"fp_{event['id']}"):
                    reclassify_event(event["id"], "safe", user["email"])
                    st.toast(tr("reclassified_done"), icon="✅")
                    st.rerun()

# ── Playground ────────────────────────────────────────────────────────────────
elif page == "nav_playground":
    st.title(tr("playground_title"))
    st.caption(tr("playground_subtitle"))

    left, right = st.columns([1, 1])
    with left:
        st.markdown(f"#### {tr('preset_scenarios')}")
        choice = st.selectbox(tr("scenario"), [item["name"] for item in DEMO_EMAILS])
        sample = next(item for item in DEMO_EMAILS if item["name"] == choice)

        st.markdown(
            f"<div class='block'>"
            f"<div style='font-size:0.84rem;color:var(--text-2);margin-bottom:4px;'>"
            f"<strong>{tr('sender')}:</strong> {sample['sender']}</div>"
            f"<div style='font-size:0.84rem;color:var(--text-2);margin-bottom:4px;'>"
            f"<strong>{tr('subject')}:</strong> {sample['subject']}</div>"
            f"<div style='font-size:0.78rem;color:var(--text-muted);'>"
            f"{tr('expected_label')}: {sample['expected_label']}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        use_llm = st.checkbox(tr("enable_llm"), value=True)
        use_vt = st.checkbox(tr("enable_vt"), value=True)

        if st.button(tr("analyze_email"), type="primary", use_container_width=True):
            with st.spinner(tr("analyzing")):
                result = classify_email(
                    sample["subject"], sample["sender"], sample["text"], use_llm, use_vt
                )
            st.session_state["last_result"] = result
            log_inference_event(
                user_email=user["email"],
                context="playground",
                subject=sample["subject"],
                sender=sample["sender"],
                text_value=sample["text"],
                result=result,
                delivered_in_smail=result["safety_verdict"] == "safe",
                expected_label=sample["expected_label"],
            )
            st.rerun()

        st.markdown("---")
        st.markdown(f"#### {tr('manual_test')}")
        with st.form("manual_form"):
            m_sender = st.text_input(tr("sender"), value="expediteur@example.com")
            m_subject = st.text_input(tr("subject"), value="Demande de confirmation")
            m_body = st.text_area(
                tr("content"), value="Pouvez-vous valider cette demande ?", height=130
            )
            submit_manual = st.form_submit_button(
                tr("analyze_email"), type="primary", use_container_width=True
            )

        if submit_manual:
            with st.spinner(tr("analyzing")):
                result = classify_email(m_subject, m_sender, m_body, True, True)
            st.session_state["last_result"] = result
            log_inference_event(
                user_email=user["email"],
                context="manual",
                subject=m_subject,
                sender=m_sender,
                text_value=m_body,
                result=result,
                delivered_in_smail=result["safety_verdict"] == "safe",
                expected_label=None,
            )
            st.rerun()

    with right:
        if st.session_state.get("last_result"):
            render_result_card(st.session_state["last_result"])
        else:
            st.info(tr("no_result_yet"))

# ── Pipeline ───────────────────────────────────────────────────────────────────
elif page == "nav_pipeline":
    if user["role"] != "admin":
        st.warning("⚠️ " + tr("admin_only"))
        st.stop()

    st.title(tr("pipeline_title"))
    st.caption(tr("pipeline_subtitle"))

    busy = st.session_state.get("pipeline_busy", False)
    if busy:
        st.warning(tr("pipeline_busy"))

    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button(tr("pipeline_base"), disabled=busy, use_container_width=True):
            st.session_state["_pipeline_pending"] = (
                tr("pipeline_base"),
                "make ingest-all-base",
            )
    with b2:
        if st.button(tr("pipeline_cron"), disabled=busy, use_container_width=True):
            st.session_state["_pipeline_pending"] = (
                tr("pipeline_cron"),
                "make ingest-all-cron",
            )
    with b3:
        if st.button(tr("pipeline_push"), disabled=busy, use_container_width=True):
            st.session_state["_pipeline_pending"] = (
                tr("pipeline_push"),
                "make pipeline-push DATASET_TAG_PREFIX=cron",
            )

    # Run OUTSIDE the columns so the terminal spans full width
    if "_pipeline_pending" in st.session_state:
        title_action, cmd_action = st.session_state.pop("_pipeline_pending")
        run_pipeline_action(title_action, cmd_action)

    if "last_pipeline_success" in st.session_state:
        if st.session_state["last_pipeline_success"]:
            st.info("✅ " + tr("pipeline_last_success"))
        else:
            st.warning("⚠️ " + tr("pipeline_last_error"))

    if output := st.session_state.get("last_pipeline_output"):
        with st.expander(tr("pipeline_output"), expanded=True):
            st.code(output, language="bash")

# ── Jeux de données ───────────────────────────────────────────────────────────
elif page == "nav_datasets":
    st.title(tr("data_platform_title"))
    st.caption(tr("data_platform_subtitle"))

    # Top-level volume stats
    raw_count = 0
    norm_count = 0
    if _data_table_exists("data_raw_record"):
        rows_raw = _data_q("SELECT COUNT(*) AS cnt FROM data_raw_record")
        raw_count = int(rows_raw[0]["cnt"]) if rows_raw else 0
    if _data_table_exists("data_normalized_message"):
        rows_norm = _data_q("SELECT COUNT(*) AS cnt FROM data_normalized_message")
        norm_count = int(rows_norm[0]["cnt"]) if rows_norm else 0

    m1, m2 = st.columns(2)
    m1.markdown(
        f"<div class='kpi'><div class='label'>{tr('total_raw')}</div>"
        f"<div class='value'>{_fmt_num(raw_count)}</div></div>",
        unsafe_allow_html=True,
    )
    m2.markdown(
        f"<div class='kpi'><div class='label'>{tr('total_normalized')}</div>"
        f"<div class='value'>{_fmt_num(norm_count)}</div></div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-bottom:16px;'></div>", unsafe_allow_html=True)

    # Source breakdown chart
    if _data_table_exists("data_source_system") and _data_table_exists(
        "data_ingestion_run"
    ):
        src_rows = _data_q("""
            SELECT
                ss.name,
                ss.source_type,
                COALESCE(SUM(ir.raw_record_count), 0) AS total_records,
                MAX(ir.finished_at) AS last_run
            FROM data_source_system ss
            LEFT JOIN data_ingestion_run ir ON ir.source_system_id = ss.id
            GROUP BY ss.id
            ORDER BY total_records DESC
            LIMIT 30
        """)
        if src_rows:
            st.markdown(f"#### {tr('source_breakdown')}")
            type_colors = {
                "api": "#1B4FCC",
                "file": "#F59E0B",
                "scraping": "#EF4444",
                "sql": "#10B981",
                "bigdata": "#8B5CF6",
                "manual": "#334155",
            }
            chart_rows = [
                {
                    "source": r["name"],
                    "count": int(r.get("total_records") or 0),
                    "type": str(r.get("source_type") or "other"),
                }
                for r in src_rows
                if int(r.get("total_records") or 0) > 0
            ]
            if chart_rows:
                spec = {
                    "mark": {
                        "type": "bar",
                        "cornerRadiusTopRight": 3,
                        "cornerRadiusBottomRight": 3,
                    },
                    "encoding": {
                        "y": {
                            "field": "source",
                            "type": "nominal",
                            "sort": "-x",
                            "axis": {"title": None, "labelFontSize": 11},
                        },
                        "x": {
                            "field": "count",
                            "type": "quantitative",
                            "axis": {"title": None, "grid": False},
                        },
                        "color": {
                            "field": "type",
                            "type": "nominal",
                            "scale": {
                                "domain": list(type_colors.keys()),
                                "range": list(type_colors.values()),
                            },
                            "legend": {"title": tr("source"), "orient": "bottom"},
                        },
                    },
                    "config": {
                        "background": "transparent",
                        "view": {"stroke": "transparent"},
                    },
                }
                st.vega_lite_chart(chart_rows, spec, width="stretch")

        # Recent ingestion runs table
        st.markdown(f"#### {tr('recent_ingestion')}")
        run_rows = _data_q("""
            SELECT ss.name, ir.status, ir.raw_record_count, ir.finished_at
            FROM data_ingestion_run ir
            JOIN data_source_system ss ON ss.id = ir.source_system_id
            WHERE ir.finished_at IS NOT NULL
            ORDER BY ir.finished_at DESC
            LIMIT 20
        """)
        if run_rows:
            for r in run_rows:
                fin = str(r.get("finished_at") or "")[:16].replace("T", " ")
                cnt = int(r.get("raw_record_count") or 0)
                ok = str(r.get("status") or "").lower() in (
                    "success",
                    "completed",
                    "done",
                )
                badge = (
                    f"<span class='badge badge-ok'>{r.get('status','')}</span>"
                    if ok
                    else f"<span class='badge badge-danger'>{r.get('status','')}</span>"
                )
                st.markdown(
                    f"<div class='card' style='padding:9px 12px;margin-bottom:4px;'>"
                    f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
                    f"<span style='font-size:0.9rem;font-weight:600;color:var(--text);'>"
                    f"{r.get('name','')}</span>{badge}</div>"
                    f"<div style='font-size:0.78rem;color:var(--text-muted);'>"
                    f"{_fmt_num(cnt)} {tr('records')} &middot; {fin}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.info(tr("no_ingestion"))
    else:
        st.info(tr("run_pipeline_hint"))
        if user["role"] == "admin" and st.button(tr("run_base_now"), type="primary"):
            run_pipeline_action(tr("pipeline_base"), "make ingest-all-base")

    # Dataset versions
    if _data_table_exists("data_dataset"):
        versions = _data_q("""
            SELECT version_tag, status, item_count, created_at
            FROM data_dataset
            ORDER BY created_at DESC
            LIMIT 24
        """)
        st.markdown(f"#### {tr('dataset_title')}")
        if not versions:
            st.info(tr("no_datasets"))
        else:
            for row in versions:
                ts = str(row.get("created_at") or "")[:16].replace("T", " ")
                ic = int(row.get("item_count") or 0)
                st.markdown(
                    f"<div class='card'>"
                    f"<strong>{row.get('version_tag','—')}</strong>"
                    f"<span style='margin-left:12px;font-size:0.82rem;color:var(--text-2);'>"
                    f"{_fmt_num(ic)} {tr('rows')} &middot; {ts} &middot; {row.get('status','')}"
                    f"</span></div>",
                    unsafe_allow_html=True,
                )

# ── Paramètres ────────────────────────────────────────────────────────────────
elif page == "nav_settings":
    st.title(tr("settings_title"))
    st.caption(tr("settings_subtitle"))

    with st.form("settings_form"):
        c1, c2 = st.columns(2)
        with c1:
            new_name = st.text_input(tr("display_name"), value=user["display_name"])
        with c2:
            lang_opts = [("fr", "Français"), ("en", "English")]
            cur_lang_idx = 0 if st.session_state.get("lang", "fr") == "fr" else 1
            new_lang_opt = st.selectbox(
                tr("language"),
                options=lang_opts,
                index=cur_lang_idx,
                format_func=lambda x: x[1],
            )
        st.text_input(tr("email"), value=user["email"], disabled=True)
        st.text_input("Rôle", value=user["role"].capitalize(), disabled=True)
        saved = st.form_submit_button(
            tr("save_settings"), type="primary", use_container_width=True
        )

    if saved:
        changed = False
        if new_name.strip() and new_name.strip() != user["display_name"]:
            _auth_exec(
                "UPDATE poc_user SET display_name = ? WHERE id = ?",
                (new_name.strip(), user["id"]),
            )
            st.session_state["user"]["display_name"] = new_name.strip()
            changed = True
        if new_lang_opt[0] != st.session_state.get("lang"):
            _set_lang(new_lang_opt[0])
            changed = True
        if changed:
            st.toast(tr("settings_saved"), icon="✅")
            st.rerun()
