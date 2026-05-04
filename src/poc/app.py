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
from datetime import datetime
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

            admin_email = os.environ.get("SICURRE_POC_ADMIN_EMAIL", "admin@sicurre.fr")
            viewer_email = os.environ.get("SICURRE_POC_VIEWER_EMAIL", "demo@sicurre.fr")
            st.caption(
                f"Comptes de démonstration : `{admin_email}` (admin) · `{viewer_email}` (viewer)"
            )
    st.stop()


# ── Authenticated App ─────────────────────────────────────────────────────────
user = st.session_state["user"]

# Sidebar
with st.sidebar:
    st.markdown(f"### 🛡️ Sicurre")
    st.markdown(
        f'<span class="badge badge-info">{user["role"].upper()}</span>',
        unsafe_allow_html=True,
    )
    st.caption(f'Connecté : {user["name"]}')
    st.markdown("---")

    pages = ["📬 Journal des menaces", "📊 Tableau de bord"]
    if is_admin():
        pages.extend(["▶️ Pipeline", "📦 Jeux de données"])

    page = st.radio("Navigation", pages, label_visibility="collapsed")
    st.markdown("---")

    if st.button("🚪 Se déconnecter", use_container_width=True):
        del st.session_state["user"]
        st.rerun()

    st.caption("Sicurre v0.1 — POC Simplon")
    st.caption("*Vos emails, protégés en 2 secondes.*")


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

    c1, c2, c3, c4 = st.columns(4)
    for col, val, lbl in [
        (c1, get_total("data_raw_record"), "Enregistrements bruts"),
        (c2, get_total("data_normalized_message"), "Messages normalisés"),
        (c3, get_total("data_annotation"), "Annotations"),
        (c4, get_total("data_dataset_item"), "Items dataset"),
    ]:
        with col:
            st.markdown(
                f'<div class="metric-card"><div class="value">{val:,}</div><div class="label">{lbl}</div></div>',
                unsafe_allow_html=True,
            )

    st.markdown("---")
    st.markdown("### Sources de données")
    sc = get_source_counts()
    if sc:
        rows_html = "".join(
            f"<tr><td>{n}</td><td style='text-align:right;font-family:JetBrains Mono,monospace'>{c:,}</td></tr>"
            for n, c in sc
        )
        st.markdown(
            f'<table class="source-tbl"><thead><tr><th>Source</th><th style="text-align:right">Nombre</th></tr></thead><tbody>{rows_html}</tbody></table>',
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.markdown("### Versions du jeu de données")
    for tag, count, status, frozen in get_dataset_versions() or []:
        bcls = "badge-legitimate" if status == "frozen" else "badge-spam"
        st.markdown(
            f'<div class="metric-card" style="text-align:left;margin-bottom:0.5rem"><strong>v{tag}</strong> <span class="badge {bcls}">{status}</span><span style="float:right;font-family:JetBrains Mono,monospace;color:var(--primary)">{count:,} items</span></div>',
            unsafe_allow_html=True,
        )


# ── Page: Pipeline (Admin) ───────────────────────────────────────────────────
elif page == "▶️ Pipeline" and is_admin():
    st.markdown("## Exécuter le pipeline")

    tab_base, tab_cron, tab_push = st.tabs(["🏗️ Base", "🔄 Cron", "📤 Push"])

    with tab_base:
        st.markdown("Reconstruit le jeu de données de base (~191k enregistrements).")
        if st.button("▶️ Lancer l'ingestion de base", key="run_base", type="primary"):
            s, t = st.empty(), st.empty()
            s.markdown("⏳ **Ingestion de base en cours…**")
            code = run_and_stream(["make", "ingest-all-base"], t, s)
            s.markdown(
                "✅ **Terminé.**" if code == 0 else f"❌ **Échec (code {code})**"
            )

    with tab_cron:
        st.markdown("Ingère les données incrémentales (cron).")
        n = st.number_input("Entrées synthétiques à générer", 0, 500, 50, 10)
        gen = st.checkbox("Générer avant le cron", True)
        if st.button("▶️ Lancer le cron", key="run_cron", type="primary"):
            s, t = st.empty(), st.empty()
            if gen and n > 0:
                s.markdown(f"⏳ **Génération de {n} entrées…**")
                run_and_stream(
                    [
                        sys.executable,
                        str(ROOT_DIR / "src/data_platform/cli/generate_sql_delta.py"),
                        "-n",
                        str(n),
                    ],
                    t,
                    s,
                )
            s.markdown("⏳ **Cron en cours…**")
            code = run_and_stream(["make", "ingest-all-cron"], t, s)
            s.markdown(
                "✅ **Terminé.**" if code == 0 else f"❌ **Échec (code {code})**"
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
    st.markdown("## Jeux de données")

    with st.form("build_form"):
        c1, c2 = st.columns(2)
        with c1:
            ds_name = st.text_input("Nom", "sicurre-core")
            vtag = st.text_input("Version", "1.0.0")
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
