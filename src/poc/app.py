"""Sicurre POC — Streamlit Dashboard with Auth & Threat Log.

A production-like POC with login, role-based access, threat log view,
and pipeline monitoring for the Sicurre data platform.
"""

import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parents[2]
DB_PATH = ROOT_DIR / "data" / "local" / "sicurre.db"

st.set_page_config(
    page_title="Sicurre — Détection de phishing",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Brand CSS ─────────────────────────────────────────────────────────────────
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&family=Sora:wght@600;700&display=swap');

:root {
    --primary: #1B4FCC; --primary-dark: #1239A6; --primary-light: #EEF3FF;
    --danger: #EF4444; --danger-bg: #FEF2F2;
    --safe: #10B981; --safe-bg: #ECFDF5;
    --warning: #F59E0B; --warning-bg: #FFFBEB;
    --surface: #FFFFFF; --border: #E2E8F0;
    --text: #0F172A; --text-sec: #475569; --text-muted: #94A3B8;
}

@media (prefers-color-scheme: dark) {
    :root {
        --primary-light: #1E3A8A;
        --danger-bg: #7F1D1D;
        --safe-bg: #064E3B;
        --warning-bg: #78350F;
        --surface: #1E293B; --border: #334155;
        --text: #F8FAFC; --text-sec: #CBD5E1; --text-muted: #64748B;
    }
}

/* Streamlit dark-mode: mirror the OS media query so both mechanisms work */
[data-theme="dark"] {
    --primary-light: #1E3A8A;
    --danger-bg: #7F1D1D;
    --safe-bg: #064E3B;
    --warning-bg: #78350F;
    --surface: #1E293B; --border: #334155;
    --text: #F8FAFC; --text-sec: #CBD5E1; --text-muted: #64748B;
}

/* Base font, but DO NOT override Material Icons used by Streamlit */
body, p, h1, h2, h3, h4, h5, h6, span:not(.material-symbols-rounded):not([class^="st-emotion-cache"]) {
    font-family: 'Inter', system-ui, sans-serif !important;
}

.main .block-container { max-width: 1100px; padding-top: 1.5rem; }
h1, h2, h3 { color: var(--text) !important; }

.login-container {
    max-width: 420px; margin: 6rem auto; padding: 2.5rem;
    background: var(--surface); border-radius: 16px;
    border: 1px solid var(--border); box-shadow: 0 8px 32px rgba(0,0,0,0.06);
}
.login-logo { text-align: center; margin-bottom: 1.5rem; }
.login-logo h1 { font-family: 'Sora', sans-serif !important; font-size: 2rem; color: var(--primary) !important; margin: 0; }
.login-logo p { color: var(--text-sec); font-size: 0.85rem; margin-top: 0.25rem; }

.metric-card {
    background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
    padding: 1.25rem; text-align: center;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04); transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.metric-card:hover { transform: translateY(-2px); box-shadow: 0 4px 16px rgba(0,0,0,0.08); }
.metric-card .value { font-size: 1.75rem; font-weight: 700; color: var(--primary); font-family: 'JetBrains Mono', monospace !important; }
.metric-card .label { font-size: 0.8rem; color: var(--text-sec); margin-top: 0.25rem; }

.badge { display: inline-block; padding: 0.15rem 0.55rem; border-radius: 999px; font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
.badge-phishing { background: var(--danger-bg); color: var(--danger); }
.badge-spam { background: var(--warning-bg); color: var(--warning); }
.badge-legitimate { background: var(--safe-bg); color: var(--safe); }
.badge-info { background: var(--primary-light); color: var(--primary); }

.threat-row {
    background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    padding: 1rem 1.25rem; margin-bottom: 0.5rem;
    display: flex; align-items: center; gap: 1rem;
    transition: border-color 0.15s ease;
}
.threat-row:hover { border-color: var(--primary); }
.threat-row .subject { font-weight: 500; color: var(--text); font-size: 0.9rem; flex: 1; }
.threat-row .meta { font-size: 0.75rem; color: var(--text-muted); }
.threat-row .confidence { font-family: 'JetBrains Mono', monospace !important; font-size: 0.8rem; color: var(--text-sec); }

.terminal-box {
    background: #0F172A; border-radius: 12px; padding: 1.25rem;
    font-family: 'JetBrains Mono', monospace !important; font-size: 0.78rem; line-height: 1.6;
    max-height: 420px; overflow-y: auto; border: 1px solid #1E293B;
    box-shadow: 0 4px 24px rgba(0,0,0,0.12);
}
.terminal-box .t-start { color: #60A5FA; } .terminal-box .t-ok { color: #34D399; }
.terminal-box .t-fail { color: #F87171; } .terminal-box .t-skip { color: #FBBF24; }
.terminal-box .t-log { color: #94A3B8; } .terminal-box .t-stage { color: #A78BFA; font-weight: 500; }
.terminal-box .t-met { color: #67E8F9; }

.source-tbl { width: 100%; border-collapse: separate; border-spacing: 0; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; font-size: 0.85rem; }
.source-tbl th { background: var(--primary-light); color: var(--primary); padding: 0.6rem 1rem; text-align: left; font-weight: 600; }
.source-tbl td { padding: 0.5rem 1rem; border-top: 1px solid var(--border); color: var(--text); }
.source-tbl tr:hover td { background: var(--surface); filter: brightness(0.95); }

.topbar { display: flex; justify-content: space-between; align-items: center; padding: 0.5rem 0; margin-bottom: 1rem; border-bottom: 1px solid var(--border); }
.topbar .greeting { font-size: 0.85rem; color: var(--text-sec); }
.topbar .role-badge { font-size: 0.7rem; }

.user-card { background: var(--primary-light); border-radius: 10px; padding: 0.75rem 1rem; margin-bottom: 0.5rem; display: flex; align-items: center; gap: 0.6rem; }
.user-card .avatar { width: 32px; height: 32px; border-radius: 50%; background: var(--primary); color: #fff; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: 0.9rem; flex-shrink: 0; }
.user-card .info { min-width: 0; }
.user-card .name { font-size: 0.82rem; font-weight: 600; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.user-card .role { font-size: 0.7rem; color: var(--text-sec); }

.sys-status { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 0.6rem 0.75rem; font-size: 0.75rem; color: var(--text-sec); }
.sys-status .dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 4px; }
.sys-status .dot-green { background: #10B981; }
.sys-status .dot-amber { background: #F59E0B; }
.sys-status .dot-gray { background: #94A3B8; }

.funnel-bar { margin: 0.4rem 0; }
.funnel-bar .bar-track { background: var(--border); border-radius: 6px; height: 22px; position: relative; overflow: hidden; }
.funnel-bar .bar-fill { height: 100%; border-radius: 6px; display: flex; align-items: center; padding: 0 0.6rem; font-size: 0.72rem; font-family: 'JetBrains Mono', monospace; color: #fff; font-weight: 500; white-space: nowrap; }
.funnel-bar .bar-label { font-size: 0.78rem; color: var(--text-sec); margin-bottom: 0.15rem; }
</style>
""",
    unsafe_allow_html=True,
)


# ── DB Helpers ────────────────────────────────────────────────────────────────
def _q(sql: str, params: tuple = ()) -> list:
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(DB_PATH))
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def get_total(table: str) -> int:
    r = _q(f"SELECT COUNT(*) FROM {table}")
    return r[0][0] if r else 0


def get_source_counts() -> list[tuple[str, int]]:
    return _q(
        "SELECT ds.name, COUNT(*) FROM data_raw_record drr JOIN data_source_system ds ON ds.id = drr.source_system_id GROUP BY ds.name ORDER BY COUNT(*) DESC"
    )


def get_dataset_versions() -> list[tuple]:
    return _q(
        "SELECT version_tag, item_count, status, frozen_at FROM data_dataset ORDER BY created_at DESC"
    )


def get_db_size_mb() -> float:
    try:
        return DB_PATH.stat().st_size / 1024 / 1024
    except FileNotFoundError:
        return 0.0


def get_label_distribution() -> dict[str, int]:
    rows = _q(
        "SELECT current_label, COUNT(*) FROM data_normalized_message GROUP BY current_label"
    )
    return {r[0]: r[1] for r in rows}


def get_ingestion_run_count() -> int:
    r = _q("SELECT COUNT(*) FROM data_ingestion_run")
    return r[0][0] if r else 0


def get_threat_samples(limit: int = 30) -> list[dict]:
    rows = _q(
        """
        SELECT dnm.id, dnm.normalized_text, dnm.current_label, dnm.text_length,
               ds.name as source_name, dnm.created_at
        FROM data_normalized_message dnm
        JOIN data_raw_record drr ON drr.id = dnm.raw_record_id
        JOIN data_raw_object dro ON dro.id = drr.raw_object_id
        JOIN data_ingestion_run dir ON dir.id = dro.ingestion_run_id
        JOIN data_source_system ds ON ds.id = dir.source_system_id
        ORDER BY dnm.created_at DESC LIMIT ?
    """,
        (limit,),
    )
    return [
        {
            "id": r[0],
            "text": r[1],
            "label": r[2],
            "length": r[3],
            "source": r[4],
            "date": r[5],
        }
        for r in rows
    ]


# ── Auth ──────────────────────────────────────────────────────────────────────
def _rate_limit_check() -> bool:
    """Simple in-memory rate limiter: max 5 login attempts per 60s."""
    now = time.time()
    attempts = st.session_state.get("_login_attempts", [])
    attempts = [t for t in attempts if now - t < 60]
    st.session_state["_login_attempts"] = attempts
    return len(attempts) < 5


def _record_attempt():
    attempts = st.session_state.get("_login_attempts", [])
    attempts.append(time.time())
    st.session_state["_login_attempts"] = attempts


def authenticate(email: str, password: str) -> dict | None:
    rows = _q(
        "SELECT id, email, display_name, password_hash, role FROM poc_user WHERE email = ?",
        (email,),
    )
    if not rows:
        return None
    uid, em, name, pw_hash, role = rows[0]
    if bcrypt.checkpw(password.encode(), pw_hash.encode()):
        return {"id": uid, "email": em, "name": name, "role": role}
    return None


def is_admin() -> bool:
    return st.session_state.get("user", {}).get("role") == "admin"


# ── Terminal Rendering ────────────────────────────────────────────────────────
STATUS_CLS = {
    "start": "t-start",
    "success": "t-ok",
    "failed": "t-fail",
    "skipped": "t-skip",
}


def render_trace(event: dict) -> str:
    if event["type"] == "trace":
        t = event["content"]
        sc = STATUS_CLS.get(t.get("status", ""), "t-log")
        met = ""
        if m := t.get("metrics"):
            met = f' <span class="t-met">[{", ".join(f"{k}={v}" for k,v in m.items())}]</span>'
        return f'<span class="t-stage">{t.get("stage","")}</span>/<span class="{sc}">{t.get("status","")}</span> {t.get("message","")}{met}'
    return f'<span class="t-log">{event["content"]}</span>'


def run_and_stream(cmd: list[str], terminal_ph, status_ph) -> int:
    lines = []
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        bufsize=1,
    )
    assert proc.stdout
    for raw in proc.stdout:
        raw = raw.rstrip()
        if not raw:
            continue
        ev = {"type": "log", "content": raw}
        if raw.startswith("{"):
            try:
                p = json.loads(raw)
                if "stage" in p and "status" in p:
                    ev = {"type": "trace", "content": p}
                    status_ph.markdown(
                        f"⏳ **{p.get('child_target','')}** — {p.get('message','')}"
                    )
            except json.JSONDecodeError:
                pass
        lines.append(render_trace(ev))
        html = '<div class="terminal-box">' + "<br>".join(lines[-150:]) + "</div>"
        terminal_ph.markdown(html, unsafe_allow_html=True)
    proc.wait()
    return proc.returncode


# ── Email Classifier (placeholder until ONNX model is ready) ──────────────────────
_PHISHING_KEYWORDS = [
    "compte suspendu",
    "vérifier",
    "urgent",
    "mot de passe",
    "cliquez",
    "connexion",
    "sécurité",
    "identifiant",
    "informations personnelles",
    "définitivement fermé",
    "sous 24h",
    "vérification requise",
    "accès bloqué",
    "carte bancaire",
    "rib",
    "virement",
    "ameli",
    "caf",
    "chronopost",
    "laposte",
    "douanes",
    "impots",
    "remboursement",
]
_SPAM_KEYWORDS = [
    "promo",
    "réduction",
    "offre",
    "gratuit",
    "remise",
    "casino",
    "gagnez",
    "félicitations",
    "sélectionné",
    "bon d’achat",
    "prix",
    "48h",
    "soldes",
    "exclusif",
    "s’abonner",
    "newsletter",
    "désinscription",
]

SAMPLE_EMAILS: list[dict] = [
    {
        "label": "phishing",
        "title": "🔴 Phishing — Usurpation La Poste",
        "text": (
            "Votre colis n° CL-847291 est en attente de livraison. Des frais de douane "
            "de 2,99€ sont dus. Votre compte La Poste a été temporairement suspendu. "
            "Veuillez vérifier vos informations sous 24h sinon votre compte sera "
            "définitivement fermé. Cliquez ici : https://laposte-secure-login.xyz/verify"
        ),
    },
    {
        "label": "spam",
        "title": "🟡 Spam — Faux bon d’achat",
        "text": (
            "FÉLICITATIONS ! Vous avez été sélectionné pour recevoir un bon d’achat de 500€ "
            "chez Amazon. Offre exclusive valable 48h seulement. Cliquez maintenant pour "
            "réclamer votre prix gratuit ! Promotion exceptionnelle, ne manquez pas cette réduction."
        ),
    },
    {
        "label": "legitimate",
        "title": "🟢 Légitime — Email professionnel",
        "text": (
            "Bonjour Monsieur Adebayo, suite à notre échange téléphonique de ce matin, "
            "je vous transmets le compte rendu de la réunion du 5 mai. Merci de bien vouloir "
            "confirmer la réception de ce message et de revenir vers moi avant vendredi. "
            "Cordialement, Marie Dupont, Responsable projet."
        ),
    },
]


def classify_email(text: str) -> dict[str, float]:
    """Placeholder classifier — keyword-based scoring.
    Replace body with ONNX model call when model is ready:
        model = onnxruntime.InferenceSession('data/models/camembertv2-phishing-fr/model.onnx')
    """
    t = text.lower()
    ph = sum(0.18 for kw in _PHISHING_KEYWORDS if kw in t)
    sp = sum(0.14 for kw in _SPAM_KEYWORDS if kw in t)
    le = max(0.05, 1.0 - ph - sp)
    total = ph + sp + le
    return {
        "phishing": round(ph / total, 3),
        "spam": round(sp / total, 3),
        "legitimate": round(le / total, 3),
    }


# ── Login Screen ──────────────────────────────────────────────────────────────
if "user" not in st.session_state:
    st.markdown(
        """
    <div class="login-container">
        <div class="login-logo">
            <h1>🛡️ Sicurre</h1>
            <p>Vos emails, protégés en 2 secondes.</p>
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )

    with st.container():
        col_spacer_l, col_form, col_spacer_r = st.columns([1, 2, 1])
        with col_form:
            with st.form("login_form"):
                email = st.text_input("Adresse email", placeholder="admin@sicurre.fr")
                password = st.text_input(
                    "Mot de passe", type="password", placeholder="••••••••"
                )
                submitted = st.form_submit_button(
                    "Se connecter", type="primary", use_container_width=True
                )

            if submitted:
                if not _rate_limit_check():
                    st.error("Trop de tentatives. Réessayez dans quelques instants.")
                elif not email or not password:
                    st.warning("Veuillez remplir tous les champs.")
                else:
                    _record_attempt()
                    user = authenticate(email, password)
                    if user:
                        st.session_state["user"] = user
                        st.rerun()
                    else:
                        st.error("Email ou mot de passe incorrect.")
    st.stop()


# ── Authenticated App ─────────────────────────────────────────────────────────
user = st.session_state["user"]

# Sidebar
with st.sidebar:
    st.markdown(
        "<p style=\"font-family:'Sora',sans-serif;font-size:1.3rem;font-weight:700;"
        'color:var(--primary);margin:0 0 0.75rem 0">🛡️ Sicurre</p>',
        unsafe_allow_html=True,
    )

    # User card
    initial = user["name"][0].upper() if user["name"] else "?"
    role_label = "Administrateur" if is_admin() else "Observateur"
    st.markdown(
        f'<div class="user-card">'
        f'<div class="avatar">{initial}</div>'
        f'<div class="info">'
        f'<div class="name">{user["name"]}</div>'
        f'<div class="role">{role_label}</div>'
        f"</div></div>",
        unsafe_allow_html=True,
    )

    st.markdown("---")

    pages = ["📬 Journal des menaces", "📊 Tableau de bord", "🤖 Classificateur"]
    if is_admin():
        pages.extend(["▶️ Pipeline", "📦 Jeux de données"])

    page = st.radio("Navigation", pages, label_visibility="collapsed")
    st.markdown("---")

    if st.button("🚪 Se déconnecter", use_container_width=True):
        del st.session_state["user"]
        st.rerun()

    # System status panel
    db_mb = get_db_size_mb()
    model_path = ROOT_DIR / "data" / "models" / "camembertv2-phishing-fr"
    model_ready = any(model_path.glob("*.onnx"))
    model_dot = "dot-green" if model_ready else "dot-amber"
    model_label = "ONNX chargé" if model_ready else "Placeholder actif"
    st.markdown(
        f'<div class="sys-status">'
        f'<div><span class="dot dot-green"></span>DB — {db_mb:.0f} MB</div>'
        f'<div style="margin-top:3px"><span class="dot {model_dot}"></span>Modèle — {model_label}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )

    # Demo mode countdown
    if st.session_state.get("demo_mode"):
        next_at = st.session_state.get("demo_next_at")
        if next_at:
            remaining = max(
                0, int((next_at - datetime.now(timezone.utc)).total_seconds())
            )
            mins, secs = divmod(remaining, 60)
            st.markdown(
                f'<div style="background:var(--safe-bg);border-radius:8px;padding:0.5rem;'
                f'text-align:center;margin-top:0.5rem">'
                f'<span style="color:#34D399;font-size:0.75rem;font-weight:600">'
                f"⏱ Cron dans {mins:02d}:{secs:02d}</span></div>",
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)
    st.caption("Sicurre v0.1 — POC Simplon 2026")


# ── Page: Threat Log ──────────────────────────────────────────────────────────
if page == "📬 Journal des menaces":
    st.markdown("## Journal des menaces")
    st.markdown("Derniers emails analysés par le système de détection Sicurre.")

    label_map = {
        "phishing": ("🔴 Phishing", "badge-phishing"),
        "spam": ("🟡 Indésirable", "badge-spam"),
        "legitimate": ("🟢 Légitime", "badge-legitimate"),
    }

    col_f1, col_f2 = st.columns(2)
    with col_f1:
        filter_label = st.selectbox(
            "Filtrer par verdict", ["Tous", "phishing", "spam", "legitimate"]
        )
    with col_f2:
        n_results = st.slider("Nombre de résultats", 10, 100, 30, step=10)

    threats = get_threat_samples(n_results)
    if filter_label != "Tous":
        threats = [t for t in threats if t["label"] == filter_label]

    if not threats:
        st.info("Aucun email analysé. Lancez le pipeline pour commencer. 🎉")
    else:
        # Summary badges
        counts = {}
        for t in threats:
            counts[t["label"]] = counts.get(t["label"], 0) + 1
        badge_html = " ".join(
            f'<span class="badge {label_map.get(l, ("?","badge-info"))[1]}" style="margin-right:0.4rem;">{label_map.get(l, (l,""))[0]} : {c}</span>'
            for l, c in sorted(counts.items())
        )
        st.markdown(badge_html, unsafe_allow_html=True)
        st.markdown("")

        for t in threats:
            label_info = label_map.get(t["label"], (t["label"], "badge-info"))
            preview = (t["text"] or "")[:120].replace("\n", " ")
            if len(t["text"] or "") > 120:
                preview += "…"
            st.markdown(
                f"""
            <div class="threat-row">
                <span class="badge {label_info[1]}">{label_info[0]}</span>
                <span class="subject">{preview}</span>
                <span class="meta">{t["source"]}</span>
                <span class="confidence">{t["length"]} car.</span>
            </div>
            """,
                unsafe_allow_html=True,
            )


# ── Page: Dashboard ───────────────────────────────────────────────────────────
elif page == "📊 Tableau de bord":
    st.markdown("## Tableau de bord")
    st.markdown(
        "Vue globale du pipeline de données — de la collecte brute au jeu de données final."
    )

    # ── Key metrics (3 meaningful numbers, not 4 identical ones) ──────────────
    raw_total = get_total("data_raw_record")
    norm_total = get_total("data_normalized_message")
    source_count = len(get_source_counts())
    run_count = get_ingestion_run_count()

    c1, c2, c3, c4 = st.columns(4)
    for col, val, lbl, hint in [
        (c1, raw_total, "Enregistrements bruts", "Collecte multi-sources"),
        (
            c2,
            norm_total,
            "Dataset final",
            f"{norm_total/raw_total*100:.1f}% retenus" if raw_total else "",
        ),
        (c3, source_count, "Sources actives", "Phishing, spam, légitimes"),
        (c4, run_count, "Runs d'ingestion", "Total historique"),
    ]:
        with col:
            st.markdown(
                f'<div class="metric-card">'
                f'<div class="value">{val:,}</div>'
                f'<div class="label">{lbl}</div>'
                f'<div style="font-size:0.68rem;color:var(--text-muted);margin-top:0.2rem">{hint}</div>'
                f"</div>",
                unsafe_allow_html=True,
            )

    st.markdown("---")

    col_left, col_right = st.columns([5, 4])

    with col_left:
        st.markdown("#### Distribution des labels")
        dist = get_label_distribution()
        total_dist = sum(dist.values()) or 1
        _DIST_META = {
            "phishing": ("🔴 Phishing", "#EF4444"),
            "spam": ("🟡 Indésirable", "#F59E0B"),
            "legitimate": ("🟢 Légitime", "#10B981"),
        }
        for lbl, (display, color) in _DIST_META.items():
            cnt = dist.get(lbl, 0)
            pct = cnt / total_dist * 100
            st.markdown(
                f'<div class="funnel-bar">'
                f'<div style="display:flex;justify-content:space-between;margin-bottom:3px">'
                f'<span style="font-size:0.8rem;color:var(--text)">{display}</span>'
                f'<span style="font-size:0.75rem;font-family:JetBrains Mono,monospace;color:var(--text-sec)">{cnt:,} ({pct:.1f}%)</span>'
                f"</div>"
                f'<div class="bar-track">'
                f'<div class="bar-fill" style="width:{pct:.1f}%;background:{color}">{pct:.0f}%</div>'
                f"</div></div>",
                unsafe_allow_html=True,
            )

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### Entonnoir pipeline")
        funnel = [
            ("Bruts collectés", raw_total, "#1B4FCC", 100.0),
            (
                "Normalisés & annotés",
                norm_total,
                "#7C3AED",
                norm_total / raw_total * 100 if raw_total else 0,
            ),
        ]
        for label, cnt, color, pct in funnel:
            bar_w = max(3, pct)
            st.markdown(
                f'<div class="funnel-bar">'
                f'<div style="display:flex;justify-content:space-between;margin-bottom:3px">'
                f'<span style="font-size:0.8rem;color:var(--text)">{label}</span>'
                f'<span style="font-size:0.75rem;font-family:JetBrains Mono,monospace;color:var(--text-sec)">{cnt:,}</span>'
                f"</div>"
                f'<div class="bar-track">'
                f'<div class="bar-fill" style="width:{bar_w:.1f}%;background:{color}">{pct:.1f}%</div>'
                f"</div></div>",
                unsafe_allow_html=True,
            )

    with col_right:
        st.markdown("#### Top 7 sources")
        sc = get_source_counts()
        top_sources = sc[:7] if sc else []
        max_src = top_sources[0][1] if top_sources else 1
        for name, cnt in top_sources:
            bar_w = max(3, cnt / max_src * 100)
            short_name = name if len(name) <= 28 else name[:25] + "…"
            st.markdown(
                f'<div style="margin:0.35rem 0">'
                f'<div style="display:flex;justify-content:space-between;margin-bottom:2px">'
                f'<span style="font-size:0.75rem;color:var(--text-sec)">{short_name}</span>'
                f'<span style="font-size:0.72rem;font-family:JetBrains Mono,monospace;color:var(--text-muted)">{cnt:,}</span>'
                f"</div>"
                f'<div style="background:var(--border);border-radius:4px;height:6px">'
                f'<div style="width:{bar_w:.1f}%;background:var(--primary);height:6px;border-radius:4px"></div>'
                f"</div></div>",
                unsafe_allow_html=True,
            )
        if len(sc) > 7:
            st.caption(f"+ {len(sc) - 7} autres sources")

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### Versions du dataset")
        versions = get_dataset_versions()
        if versions:
            for tag, count, status, frozen in versions:
                bcls = "badge-legitimate" if status == "frozen" else "badge-spam"
                frozen_str = f" · gelé {frozen[:10]}" if frozen else ""
                st.markdown(
                    f'<div style="background:var(--surface);border:1px solid var(--border);'
                    f'border-radius:8px;padding:0.6rem 0.75rem;margin-bottom:0.4rem">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center">'
                    f'<span style="font-size:0.8rem;font-weight:600;color:var(--text)">{tag}</span>'
                    f'<span class="badge {bcls}">{status}</span>'
                    f"</div>"
                    f'<div style="font-size:0.72rem;color:var(--text-muted);margin-top:2px">'
                    f"{count:,} items{frozen_str}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.caption("Aucun dataset construit. Lancez le pipeline push.")


# ── Page: Pipeline (Admin) ───────────────────────────────────────────────────
elif page == "▶️ Pipeline" and is_admin():
    st.markdown("## Exécuter le pipeline")

    tab_base, tab_cron, tab_push = st.tabs(["🏗️ Base", "🔄 Cron", "📤 Push"])

    with tab_base:
        st.markdown("### Ingestion de base")
        st.markdown(
            "Télécharge et insère **tous les enregistrements historiques** depuis les 5 sources "
            "(PhishTank, CERT-FR, CSV, Base de données, Common Crawl) vers `sicurre.db`.\n\n"
            "- Durée typique : **15–45 min** · environ 194 000 enregistrements bruts\n"
            "- Résultat : **~32 000 messages normalisés** après déduplication + filtrage\n"
            "- **Idempotent** : relancer ne crée pas de doublons — les runs existants sont ignorés\n"
            "- Si un dataset existe déjà, cette action ne le supprime pas — seule l'ingestion est rejouée"
        )
        st.warning(
            "⚠️ Ce bouton efface et réinsère les données brutes. "
            "À réserver au démo initial ou à une réinitialisation complète.",
            icon="⚠️",
        )
        if st.button("▶️ Lancer l'ingestion de base", key="run_base", type="primary"):
            s, t = st.empty(), st.empty()
            s.markdown("⏳ **Ingestion de base en cours…**")
            code = run_and_stream(["make", "ingest-all-base"], t, s)
            s.markdown(
                "✅ **Terminé.**" if code == 0 else f"❌ **Échec (code {code})**"
            )

    with tab_cron:
        st.markdown("### Ingestion incrémentale (cron)")
        st.markdown(
            "Lance tous les collecteurs en séquence : **PhishTank → CERT-FR → CSV → "
            "Base de données → Common Crawl**. La durée du crawl CC est contrôlée par "
            "`SICURRE_CC_CRON_DURATION_MODE` dans `.env` "
            "(`short` = 30 min · `standard` = 8 h)."
        )

        # ─ Manual trigger ──────────────────────────────────────────────────────
        col_run, col_gen = st.columns(2)
        with col_run:
            if st.button(
                "▶️ Lancer le cron maintenant", key="run_cron", type="primary"
            ):
                s_ph, t_ph = st.empty(), st.empty()
                s_ph.markdown("⏳ **Cron en cours…**")
                code = run_and_stream(["make", "ingest-all-cron"], t_ph, s_ph)
                s_ph.markdown(
                    "✅ **Terminé.**" if code == 0 else f"❌ **Échec (code {code})**"
                )
        with col_gen:
            n_gen = st.number_input("Entrées DB synthétiques à générer", 0, 500, 50, 10)
            if st.button("🔧 Générer delta DB", key="run_gen"):
                s_ph, t_ph = st.empty(), st.empty()
                run_and_stream(
                    [
                        sys.executable,
                        str(ROOT_DIR / "src/data_platform/cli/generate_sql_delta.py"),
                        "-n",
                        str(n_gen),
                    ],
                    t_ph,
                    s_ph,
                )

        st.markdown("---")
        st.markdown("#### 🎬 Mode démo — déclenchement automatique")
        st.markdown(
            "Démarre un minuteur récurrent. Le cron se déclenche automatiquement "
            "toutes les N minutes à partir du moment où vous cliquez ▶ Démarrer."
        )

        col_int, col_btn = st.columns([3, 1])
        with col_int:
            demo_interval = st.number_input(
                "Intervalle (minutes)",
                min_value=1,
                max_value=60,
                value=st.session_state.get("demo_interval_minutes", 5),
                step=1,
            )
        with col_btn:
            st.markdown("<br>", unsafe_allow_html=True)
            if not st.session_state.get("demo_mode"):
                if st.button("▶ Démarrer", key="start_demo", type="primary"):
                    st.session_state["demo_mode"] = True
                    st.session_state["demo_interval_minutes"] = demo_interval
                    st.session_state["demo_next_at"] = datetime.now(
                        timezone.utc
                    ) + timedelta(minutes=demo_interval)
                    st.session_state["demo_cron_last_fired"] = None
                    st.rerun()
            else:
                if st.button("⏹ Arrêter", key="stop_demo"):
                    st.session_state["demo_mode"] = False
                    st.session_state.pop("demo_next_at", None)
                    st.rerun()

        if st.session_state.get("demo_mode"):
            next_at = st.session_state.get("demo_next_at")
            if next_at:
                now = datetime.now(timezone.utc)
                if now >= next_at:
                    # Timer fired — run cron and reset
                    interval_m = st.session_state.get("demo_interval_minutes", 5)
                    st.session_state["demo_next_at"] = now + timedelta(
                        minutes=interval_m
                    )
                    st.session_state["demo_cron_last_fired"] = now.strftime("%H:%M:%S")
                    s_ph, t_ph = st.empty(), st.empty()
                    s_ph.markdown("🔄 **Mode démo — cron automatique en cours…**")
                    code = run_and_stream(["make", "ingest-all-cron"], t_ph, s_ph)
                    s_ph.markdown(
                        "✅ **Cron automatique terminé.**"
                        if code == 0
                        else f"❌ **Cron automatique échoué (code {code})**"
                    )
                else:
                    remaining = max(0, int((next_at - now).total_seconds()))
                    mins, secs = divmod(remaining, 60)
                    st.markdown(
                        f'<div style="background:#064E3B;border-radius:10px;padding:1rem;'
                        f'text-align:center;margin:0.75rem 0">'
                        f'<span style="color:#34D399;font-size:1.4rem;font-family:JetBrains Mono,monospace">'
                        f"⏱ {mins:02d}:{secs:02d}</span><br>"
                        f'<span style="color:#6EE7B7;font-size:0.75rem">'
                        f"Prochain cron automatique · toutes les "
                        f'{st.session_state["demo_interval_minutes"]} min</span></div>',
                        unsafe_allow_html=True,
                    )

            if last := st.session_state.get("demo_cron_last_fired"):
                st.success(f"Dernier déclenchement automatique : {last}")

            # Live 1-second refresh for the countdown
            time.sleep(1)
            st.rerun()
        else:
            st.info(
                "Mode démo désactivé. Définissez un intervalle et cliquez sur ▶ Démarrer."
            )

    with tab_push:
        st.markdown("Normalisation puis ecriture des annotations manquantes.")
        if st.button("▶️ Lancer pipeline push", key="run_push", type="primary"):
            s, t = st.empty(), st.empty()
            for name, tgt in [
                ("Normalisation", "normalize"),
                ("Annotation", "annotate"),
            ]:
                s.markdown(f"⏳ **{name}…**")
                code = run_and_stream(["make", tgt], t, s)
                if code != 0:
                    s.markdown(f"❌ **{name} échouée**")
                    break
            else:
                s.markdown("✅ **Pipeline push terminé.**")


# ── Page: Datasets (Admin) ───────────────────────────────────────────────────
elif page == "📦 Jeux de données" and is_admin():
    st.markdown("## 📦 Jeux de données (Dataset Management)")
    st.markdown(
        "Construit et exporte des **snapshots versionnés** du dataset pour l'entraînement du modèle.\n\n"
        "| Action | Ce qui se passe |\n"
        "|--------|-----------------|\n"
        "| **Construire** | Crée une nouvelle entrée dans `data_dataset` avec un tag unique (ex. `base-20260506-…`). Les items du pipeline sont figés dans `data_dataset_item`. Chaque build = une **nouvelle version** — rien n'est écrasé. |\n"
        "| **Exporter** | Envoie le dataset vers R2 sous `raw-snapshots/training_dataset/<version_tag>/train|val|test/`. |\n\n"
        "Le tag de version est préfixé `base-` ou `cron-` selon l'origine du build."
    )
    st.markdown("---")

    with st.form("build_form"):
        c1, c2 = st.columns(2)
        with c1:
            ds_name = st.text_input("Nom", "sicurre-core")
            auto_tag = datetime.now(timezone.utc).strftime("base-%Y%m%d-%H%M%S")
            vtag = st.text_input("Version (tag auto-généré, modifiable)", auto_tag)
        with c2:
            usage = st.selectbox("Usage", ["training", "evaluation"])
        submitted = st.form_submit_button("🔨 Construire", type="primary")

    if submitted:
        s, t = st.empty(), st.empty()
        s.markdown(f"⏳ **Construction v{vtag}…**")
        code = run_and_stream(
            [
                sys.executable,
                str(ROOT_DIR / "src/data_platform/cli/datasets/build.py"),
                "--name",
                ds_name,
                "--version-tag",
                vtag,
                "--target-usage",
                usage,
                "--write",
            ],
            t,
            s,
        )
        s.markdown(
            f"✅ **v{vtag} construit.**" if code == 0 else f"❌ **Échec (code {code})**"
        )

    st.markdown("---")
    st.markdown("### Versions existantes")
    for tag, count, status, frozen in get_dataset_versions() or []:
        c1, c2 = st.columns([4, 1])
        with c1:
            bcls = "badge-legitimate" if status == "frozen" else "badge-spam"
            st.markdown(
                f'**v{tag}** <span class="badge {bcls}">{status}</span> — `{count:,}` items',
                unsafe_allow_html=True,
            )
        with c2:
            if st.button(f"📥 Exporter", key=f"exp_{tag}"):
                s, t = st.empty(), st.empty()
                run_and_stream(
                    [
                        sys.executable,
                        str(ROOT_DIR / "src/data_platform/cli/datasets/export.py"),
                        "--version-tag",
                        tag,
                    ],
                    t,
                    s,
                )


# ── Page: Classificateur ──────────────────────────────────────────────────────
elif page == "🤖 Classificateur":
    model_path_cls = ROOT_DIR / "data" / "models" / "camembertv2-phishing-fr"
    model_ready_cls = any(model_path_cls.glob("*.onnx"))

    st.markdown("## 🤖 Classificateur d'emails")
    if model_ready_cls:
        st.success(
            "✅ Modèle CamemBERTav2 ONNX chargé depuis `data/models/camembertv2-phishing-fr/`",
            icon="✅",
        )
    else:
        st.info(
            "**Modèle placeholder actif** — Le moteur heuristique ci-dessous simule la "
            "classification jusqu'à ce que le modèle CamemBERTav2 fine-tuné soit disponible.\n\n"
            "**Prochaine étape :** entraîner sur Databricks (MLflow expérience "
            "`sicurre-camembertav2-phishing-fr`), exporter en ONNX INT8, déposer dans "
            "`data/models/camembertv2-phishing-fr/model.onnx`.",
        )

    # Roadmap accordion
    with st.expander(
        "🗺️ Feuille de route — Du dataset au modèle en production", expanded=False
    ):
        st.markdown("""
| Étape | Statut | Description |
|-------|--------|-------------|
| 1. Collecte de données | ✅ Fait | 194 000 emails multi-sources, 27 sources, 3 classes |
| 2. Normalisation & annotation | ✅ Fait | 32 288 messages filtrés, dédupliqués, annotés |
| 3. Export dataset | ✅ Fait | `base-20260506-075504` → R2 (train/val/test splits) |
| 4. Fine-tuning CamemBERTav2 | ⏳ En cours | Databricks + MLflow, ONNX INT8 export |
| 5. Intégration modèle ONNX | 🔜 Planifié | Remplacer `classify_email()` par `OnnxClassifier` |
| 6. Gmail Pub/Sub live | 🔜 Planifié | Cloud Run listener → phishing-api → Gmail Trash |
| 7. Alerte temps réel (<2 s) | 🔜 Planifié | Fin-to-fin : réception → verdict → action Gmail |
            """)

    _LABEL_META = {
        "phishing": ("🔴 Phishing", "badge-phishing", "#EF4444"),
        "spam": ("🟡 Indésirable", "badge-spam", "#F59E0B"),
        "legitimate": ("🟢 Légitime", "badge-legitimate", "#10B981"),
    }

    def _render_result(scores: dict[str, float]) -> None:
        top_label = max(scores, key=scores.__getitem__)
        label_text, badge_cls, color = _LABEL_META.get(
            top_label, (top_label, "badge-info", "#1B4FCC")
        )
        # Use CSS vars for background — only border/text color remains hardcoded per-label
        st.markdown(
            f'<div style="background:var(--surface);border:2px solid {color};'
            f'border-radius:12px;padding:1.25rem;margin:0.75rem 0">'
            f'<div style="font-size:1.05rem;font-weight:700;color:{color}'
            f';margin-bottom:0.75rem">Verdict : {label_text}</div>',
            unsafe_allow_html=True,
        )
        for lbl, score in sorted(scores.items(), key=lambda x: -x[1]):
            lmeta = _LABEL_META.get(lbl, (lbl, "badge-info", "#1B4FCC"))
            pct = int(score * 100)
            bar_w = max(2, pct)
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:0.75rem;margin:0.4rem 0">'
                f'<span style="width:90px;font-size:0.8rem;color:var(--text-sec)">'
                f"{lmeta[0]}</span>"
                f'<div style="flex:1;background:var(--border);border-radius:4px;height:10px">'
                f'<div style="width:{bar_w}%;background:{lmeta[2]};height:10px;'
                f'border-radius:4px;transition:width 0.5s ease"></div></div>'
                f'<span style="width:45px;text-align:right;font-family:JetBrains Mono,monospace;'
                f'font-size:0.8rem;color:var(--text)">{pct}%</span></div>',
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)

    tab_manual, tab_demo = st.tabs(["✍️ Analyse manuelle", "🎞️ Démo automatique"])

    with tab_manual:
        st.markdown("Collez le corps d'un email pour l'analyser.")
        user_text = st.text_area(
            "Texte de l'email",
            placeholder="Coller ici le contenu de l'email à analyser…",
            height=160,
        )
        if st.button("🔍 Analyser", type="primary", key="classify_manual"):
            if not user_text.strip():
                st.warning("Veuillez saisir un texte.")
            else:
                with st.spinner("Classification en cours…"):
                    time.sleep(0.4)  # Simulate model inference latency
                    scores = classify_email(user_text)
                _render_result(scores)

        model_path = ROOT_DIR / "data" / "models" / "camembertv2-phishing-fr"
        model_ready = any(model_path.glob("*.onnx"))
        if model_ready:
            st.success(
                "✅ Modèle ONNX chargé depuis `data/models/camembertv2-phishing-fr/`"
            )
        else:
            st.info(
                "⚙️ Modèle ONNX non encore disponible — "
                "classificateur heuristique actif (placeholder). "
                "Entraînez le modèle et déposez `model.onnx` dans "
                "`data/models/camembertv2-phishing-fr/` pour activer l'inférence réelle."
            )

    with tab_demo:
        st.markdown(
            "Simulation d'arrivée d'emails en temps réel. "
            "Cliquez sur un exemple pour le classifier instantanément."
        )
        for i, sample in enumerate(SAMPLE_EMAILS):
            with st.container():
                col_info, col_btn = st.columns([5, 1])
                with col_info:
                    st.markdown(f"**{sample['title']}**")
                    preview = sample["text"][:110].replace("\n", " ") + "…"
                    st.caption(preview)
                with col_btn:
                    if st.button("Analyser", key=f"sample_{i}"):
                        st.session_state[f"sample_result_{i}"] = classify_email(
                            sample["text"]
                        )
                if result := st.session_state.get(f"sample_result_{i}"):
                    _render_result(result)
                st.markdown("---")

        st.markdown("#### 🔴 Simulation temps réel — email entrant")
        st.markdown(
            "Cette section simulera l'arrivée d'un email via Gmail Pub/Sub "
            "et son passage dans le classificateur en moins de 2 secondes. "
            "*(Disponible une fois le modèle et l'intégration Gmail câblés.)*"
        )
        if st.button("📨 Simuler un email entrant", key="simulate_incoming"):
            import random

            chosen = random.choice(SAMPLE_EMAILS)
            with st.spinner("📡 Email reçu via Pub/Sub… Classification en cours…"):
                time.sleep(1.2)
            scores = classify_email(chosen["text"])
            top = max(scores, key=scores.__getitem__)
            icon = {"phishing": "🚨", "spam": "⚠️", "legitimate": "✅"}.get(top, "🔍")
            st.markdown(
                f'<div style="border-left:4px solid '
                f'{"#EF4444" if top=="phishing" else "#F59E0B" if top=="spam" else "#10B981"}'
                f";padding:0.75rem 1rem;background:var(--surface);border-radius:0 8px 8px 0;"
                f'margin:0.5rem 0">'
                f"<strong>{icon} Alerte Sicurre</strong> — "
                f"Email classifié comme <strong>{top}</strong> en 1.2 s<br>"
                f'<span style="font-size:0.8rem;color:var(--text-sec)">'
                f'Sujet (simulé) : {chosen["title"]}</span></div>',
                unsafe_allow_html=True,
            )
            _render_result(scores)
