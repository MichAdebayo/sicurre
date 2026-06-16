from __future__ import annotations

import sys
from pathlib import Path

# Add project root to sys.path to resolve src.poc imports
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

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
from typing import Any
from uuid import uuid4

import bcrypt
import httpx
import streamlit as st
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError

try:
    from poc.local_runtime import (
        POC_AUTH_DB_PATH,
        POC_DATA_DB_PATH,
        build_poc_command_env,
        ensure_local_auth_db,
    )
except ModuleNotFoundError:
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

INFERENCE_URL = os.environ.get(
    "SICURRE_POC_INFERENCE_API_URL", "http://127.0.0.1:8000/v1/classify"
)
INFERENCE_API_KEY = os.environ.get(
    "SICURRE_POC_INFERENCE_API_KEY", os.environ.get("INFERENCE_API_KEY", "")
)

# ── Dynamic Theme Mode Override ──────────────────────────────────────────────
if "theme_mode" not in st.session_state:
    st.session_state["theme_mode"] = "System"

theme_mode = st.session_state["theme_mode"]
force_theme_css = ""
if theme_mode == "Light":
    force_theme_css = """
  :root {
    --bg: #F1F5F9 !important;
    --surface: #FFFFFF !important;
    --border: #CBD5E1 !important;
    --border-line: #CBD5E1 !important;
    --text: #0F2E7A !important;
    --text-2: #334155 !important;
    --text-muted: #64748B !important;
    --cta-text: #102A43 !important;
    --empty-text: #334155 !important;
    --primary: #1B4FCC !important;
    --primary-dark: #1239A6 !important;
    --primary-light: #EEF3FF !important;
    --primary-border: #CBD5E1 !important;
    --accent: #F59E0B !important;
    --accent-dark: #B45309 !important;
    --danger: #D97706 !important;
    --danger-bg: #FFFBEB !important;
    --danger-border: #FDE68A !important;
    --nav-hover: #EEF3FF !important;
    --danger-semantic: #EF4444 !important;
    --safe-semantic: #10B981 !important;
  }
  """
elif theme_mode == "Dark":
    force_theme_css = """
  :root {
    --bg: #1E293B !important;
    --surface: #334155 !important;
    --border: #475569 !important;
    --border-line: rgba(255, 255, 255, 0.25) !important;
    --text: #F1F5F9 !important;
    --text-2: #CBD5E1 !important;
    --text-muted: #94A3B8 !important;
    --cta-text: #111827 !important;
    --empty-text: #F8FAFC !important;
    --primary: #60A5FA !important;
    --primary-dark: #3B82F6 !important;
    --primary-light: #1E3A5F !important;
    --primary-border: #475569 !important;
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
  div[data-testid="stFormSubmitButton"] button:active * { color: #FFFFFF !important; }

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
    f"""
<style>
{force_theme_css}
/* ── Light mode tokens ────────────────────────────────── */
:root {{
  --bg: #F1F5F9;
  --surface: #FFFFFF;
  --border: #CBD5E1;
  --border-line: #CBD5E1;
  --text: #0F2E7A;
  --text-2: #334155;
  --text-muted: #64748B;
  --cta-text: #102A43;
  --empty-text: #334155;
  --primary: #1B4FCC;
  --primary-dark: #1239A6;
  --primary-light: #EEF3FF;
  --primary-border: #CBD5E1;
  --accent: #F59E0B;
  --accent-dark: #B45309;
  --danger: #D97706;
  --danger-bg: #FFFBEB;
  --danger-border: #FDE68A;
  --safe: #10B981;
  --safe-bg: #ECFDF5;
  --safe-border: #A7F3D0;
  --warning: #F59E0B;
  --warning-bg: #FFFBEB;
  --warning-border: #FDE68A;
  --nav-hover: #EEF3FF;
  --shadow: 0 1px 3px rgba(0,0,0,0.08);
  --danger-semantic: #EF4444;
  --safe-semantic: #10B981;
}}

/* ── Dark mode tokens (OS preference) ────────────────── */
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #1E293B;
    --surface: #334155;
    --border: #475569;
    --border-line: rgba(255, 255, 255, 0.25);
    --text: #F1F5F9;
    --text-2: #CBD5E1;
    --text-muted: #94A3B8;
    --cta-text: #111827;
    --empty-text: #F8FAFC;
    --primary: #60A5FA;
    --primary-dark: #3B82F6;
    --primary-light: #1E3A5F;
    --primary-border: #475569;
    --accent: #F59E0B;
    --accent-dark: #B45309;
    --danger: #F59E0B;
    --danger-bg: #451A03;
    --danger-border: #78350F;
    --safe: #34D399;
    --safe-bg: #022C22;
    --safe-border: #064E3B;
    --warning: #FBBF24;
    --warning-bg: #451A03;
    --warning-border: #78350F;
    --nav-hover: #1E3A5F;
    --shadow: 0 1px 3px rgba(0,0,0,0.4);
    --danger-semantic: #EF4444;
    --safe-semantic: #34D399;
  }}
}}

/* ── Streamlit dark theme ──────────────────────────────── */
[data-theme="dark"] {{
  --bg: #1E293B; --surface: #334155; --border: #475569;
  --border-line: rgba(255, 255, 255, 0.25);
  --text: #F1F5F9; --text-2: #CBD5E1; --text-muted: #94A3B8;
  --cta-text: #111827; --empty-text: #F8FAFC;
  --primary: #60A5FA; --primary-dark: #3B82F6;
  --primary-light: #1E3A5F; --primary-border: #475569;
  --accent: #F59E0B; --accent-dark: #B45309;
  --danger: #F59E0B; --danger-bg: #451A03; --danger-border: #78350F;
  --safe: #34D399; --safe-bg: #022C22; --safe-border: #064E3B;
  --warning: #FBBF24; --warning-bg: #451A03; --warning-border: #78350F;
  --nav-hover: #1E3A5F; --shadow: 0 1px 3px rgba(0,0,0,0.4);
  --danger-semantic: #EF4444; --safe-semantic: #34D399;
}}

/* ── App shell ─────────────────────────────────────────── */
.stApp {{ background: var(--bg) !important; color: var(--text) !important; }}

[data-testid="stHeader"] {{
  background: var(--surface) !important;
  border-bottom: 1px solid var(--border) !important;
}}

[data-testid="stSidebar"] {{
  background: var(--surface) !important;
  border-right: 1px solid var(--border) !important;
}}

/* ── Hide chrome ───────────────────────────────────────── */
#MainMenu {{ visibility: hidden; }}
footer {{ visibility: hidden; }}
[data-testid="stDeployButton"] {{ display: none; }}

/* ── Logo background fix for dark mode clash ──────────── */
.logo-container {{
  display: inline-flex;
  align-items: center;
  justify-content: center;
}}

/* ── Global action buttons (primary CTA) ──────────────── */
button[data-testid^="stBaseButton-primary"],
button[kind="primaryFormSubmit"],
button[data-testid="stBaseButton-primaryFormSubmit"],
.stButton > button[kind="primary"],
div[data-testid="stFormSubmitButton"] button {{
  background: var(--accent) !important;
  color: var(--cta-text) !important;
  border: 1px solid var(--accent) !important;
  border-radius: 8px !important;
  font-weight: 600 !important;
  transition: all 0.15s ease !important;
}}
button[data-testid^="stBaseButton-primary"] *,
button[kind="primaryFormSubmit"] *,
button[data-testid="stBaseButton-primaryFormSubmit"] *,
.stButton > button[kind="primary"] *,
div[data-testid="stFormSubmitButton"] button * {{
  color: var(--cta-text) !important;
}}

/* Login helper text must stay readable on dark surfaces */
[data-testid="InputInstructions"],
[data-testid="InputInstructions"] *,
[data-testid="InputInstructions"] span,
[data-testid="InputInstructions"] span * {{
  color: var(--empty-text) !important;
  opacity: 1 !important;
}}

/* Sidebar nav must stay readable on hover/focus even when the generic CTA rule applies */
[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"],
[data-testid="stSidebar"] button[kind="primary"] {{
  color: var(--text) !important;
}}
[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"] *,
[data-testid="stSidebar"] button[kind="primary"] * {{
  color: var(--text) !important;
}}

/* Ensure form submit buttons (login) keep readable text */
[data-testid="stForm"] div[data-testid="stFormSubmitButton"] button,
[data-testid="stForm"] div[data-testid="stFormSubmitButton"] button * {{
  color: var(--cta-text) !important;
}}

button[data-testid^="stBaseButton-primary"]:hover,
button[data-testid^="stBaseButton-primary"]:focus,
button[data-testid^="stBaseButton-primary"]:active,
button[data-testid="stBaseButton-primaryFormSubmit"]:hover,
button[data-testid="stBaseButton-primaryFormSubmit"]:focus,
button[data-testid="stBaseButton-primaryFormSubmit"]:active,
button[kind="primaryFormSubmit"]:hover,
button[kind="primaryFormSubmit"]:focus,
button[kind="primaryFormSubmit"]:active,
button[data-testid^="stBaseButton-primary"]:hover *,
button[data-testid^="stBaseButton-primary"]:focus *,
button[data-testid^="stBaseButton-primary"]:active *,
button[kind="primaryFormSubmit"]:hover *,
button[kind="primaryFormSubmit"]:focus *,
button[kind="primaryFormSubmit"]:active *,
.stButton > button[kind^="primary"]:hover,
.stButton > button[kind^="primary"]:focus,
.stButton > button[kind^="primary"]:active,
.stButton > button[kind^="primary"]:hover *,
.stButton > button[kind^="primary"]:focus *,
.stButton > button[kind^="primary"]:active *,
div[data-testid="stFormSubmitButton"] button:hover,
div[data-testid="stFormSubmitButton"] button:focus,
div[data-testid="stFormSubmitButton"] button:active,
div[data-testid="stFormSubmitButton"] button:hover *,
div[data-testid="stFormSubmitButton"] button:focus *,
div[data-testid="stFormSubmitButton"] button:active * {{
  background: var(--accent-dark) !important;
  border-color: var(--accent-dark) !important;
  color: #FFFFFF !important;
}}

/* Sidebar nav focus/hover must stay on the readable text token, not the dark CTA token */
[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"]:hover,
[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"]:focus,
[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"]:active,
[data-testid="stSidebar"] button[kind="primary"]:hover,
[data-testid="stSidebar"] button[kind="primary"]:focus,
[data-testid="stSidebar"] button[kind="primary"]:active {{
  color: var(--text) !important;
  background: var(--nav-hover) !important;
}}
[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"]:hover *,
[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"]:focus *,
[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"]:active *,
[data-testid="stSidebar"] button[kind="primary"]:hover *,
[data-testid="stSidebar"] button[kind="primary"]:focus *,
[data-testid="stSidebar"] button[kind="primary"]:active * {{
  color: var(--text) !important;
}}
button[data-testid^="stBaseButton-primary"]:hover *,
button[data-testid^="stBaseButton-primary"]:focus *,
button[data-testid^="stBaseButton-primary"]:active *,
button[kind="primaryFormSubmit"]:hover *,
button[kind="primaryFormSubmit"]:focus *,
button[kind="primaryFormSubmit"]:active *,
.stButton > button[kind="primary"]:hover *,
.stButton > button[kind="primary"]:focus *,
.stButton > button[kind="primary"]:active *,
div[data-testid="stFormSubmitButton"] button:hover *,
div[data-testid="stFormSubmitButton"] button:focus *,
div[data-testid="stFormSubmitButton"] button:active * {{
  color: #FFFFFF !important;
}}

/* ── Secondary buttons ────────────────────────────────── */
button[data-testid="stBaseButton-secondary"] {{
  border: 1px solid var(--border) !important;
  background: var(--surface) !important;
  color: var(--text-2) !important;
  border-radius: 8px !important;
  font-weight: 500 !important;
  transition: all 0.15s ease !important;
}}
button[data-testid="stBaseButton-secondary"]:hover {{
  border-color: var(--accent) !important;
  background: var(--primary-light) !important;
  color: var(--text) !important;
}}

/* ── Phishing Red Alert Button (Smail simulation) ──────── */
button[aria-label="Signaler comme phishing"],
button[aria-label="Report as phishing"] {{
  background-color: var(--danger-semantic) !important;
  border-color: var(--danger-semantic) !important;
  color: #FFFFFF !important;
}}
button[aria-label="Signaler comme phishing"]:hover,
button[aria-label="Report as phishing"]:hover {{
  background-color: #DC2626 !important;
  border-color: #DC2626 !important;
  color: #FFFFFF !important;
}}

/* ── Forms ────────────────────────────────────────────── */
[data-testid="stForm"] {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
}}

/* ── Focus rings & Text Contrast on input fields ─────── */
div[data-baseweb="input"] > div {{
  transition: border-color 0.15s ease-in-out, box-shadow 0.15s ease-in-out !important;
}}
div[data-baseweb="input"]:focus-within,
div[data-baseweb="textarea"]:focus-within,
div[data-baseweb="input"]:focus-within > div,
div[data-baseweb="textarea"]:focus-within > div {{
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 1px var(--accent) !important;
}}
input[data-testid="stTextInput-Input"]:focus,
textarea[data-testid="stTextArea-Input"]:focus {{
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 1px var(--accent) !important;
}}

input[data-testid="stTextInput-Input"],
textarea[data-testid="stTextArea-Input"],
div[data-baseweb="input"] input,
div[data-baseweb="textarea"] textarea,
[data-baseweb="select"] div,
[data-baseweb="select"] select {{
  color: var(--text) !important;
}}

/* Disabled text inputs in dark and light modes ───────── */
div[data-baseweb="input"] input:disabled,
div[data-baseweb="textarea"] textarea:disabled,
div[data-baseweb="input"] input[disabled],
div[data-baseweb="textarea"] textarea[disabled] {{
  color: var(--text-2) !important;
  -webkit-text-fill-color: var(--text-2) !important;
  background-color: var(--bg) !important;
  opacity: 1 !important;
  cursor: not-allowed !important;
}}
div[data-baseweb="input"]:has(input:disabled),
div[data-baseweb="input"]:has(input[disabled]) {{
  background-color: var(--bg) !important;
  border-color: var(--border) !important;
  opacity: 1 !important;
}}

div[data-baseweb="input"],
div[data-baseweb="textarea"],
div[data-baseweb="select"] {{
  background-color: var(--surface) !important;
  border: 1px solid var(--border) !important;
}}

div[data-baseweb="input"] *,
div[data-baseweb="textarea"] *,
div[data-baseweb="select"] * {{
  background-color: transparent !important;
}}
input::placeholder,
textarea::placeholder,
input[data-testid="stTextInput-Input"]::placeholder,
textarea[data-testid="stTextArea-Input"]::placeholder {{
  color: var(--text-muted) !important;
  opacity: 0.8 !important;
}}

/* Popover select menu dropdown contrast */
div[data-baseweb="popover"] div,
div[data-baseweb="popover"] span,
[role="listbox"] li,
[role="listbox"] div {{
  color: var(--text-2) !important;
  background-color: var(--surface) !important;
}}
[role="listbox"] li:hover,
[role="listbox"] div:hover {{
  background-color: var(--primary-light) !important;
  color: var(--primary) !important;
}}

/* ── Checkboxes ───────────────────────────────────────── */
input[type="checkbox"] {{
  accent-color: var(--accent) !important;
}}
[data-testid="stCheckbox"] label,
[data-testid="stCheckbox"] span,
[data-testid="stCheckbox"] div,
[data-baseweb="checkbox"] span,
[data-baseweb="checkbox"] div {{
  color: var(--text-2) !important;
}}
div[data-baseweb="checkbox"] > div:first-child {{
  border-color: var(--border) !important;
}}
div[data-baseweb="checkbox"]:focus-within > div:first-child {{
  border-color: var(--accent) !important;
}}
div[data-baseweb="checkbox"] input:checked + div {{
  background-color: var(--accent) !important;
  border-color: var(--accent) !important;
}}
div[data-baseweb="checkbox"] input:checked + div svg {{
  fill: #FFFFFF !important;
  stroke: #FFFFFF !important;
}}
div[data-baseweb="checkbox"]:hover div {{
  border-color: var(--accent) !important;
}}

/* ── Streamlit Tabs active highlight ──────────────────── */
button[data-baseweb="tab"] {{
  color: var(--text-muted) !important;
  transition: color 0.15s ease !important;
}}
button[data-baseweb="tab"]:hover {{
  color: var(--accent) !important;
}}
button[data-baseweb="tab"][aria-selected="true"] {{
  color: var(--accent) !important;
  border-bottom-color: var(--accent) !important;
}}
div[data-baseweb="tab-highlight"] {{
  background-color: var(--accent) !important;
}}

/* ── Sidebar spacing & positioning ────────────────────── */
[data-testid="stSidebarUserContent"] {{
  padding-top: 2rem !important;
  padding-bottom: 0.4rem !important;
  display: flex !important;
  flex-direction: column !important;
  height: 100% !important;
}}
/* Show header but make it transparent so collapse button is visible */
[data-testid="stSidebarHeader"] {{
  background: transparent !important;
  border: none !important;
  padding: 0 !important;
  min-height: 0 !important;
}}
[data-testid="stSidebarCollapseButton"] {{
  position: absolute !important;
  top: 0.8rem !important;
  right: 0.25rem !important;
  z-index: 10 !important;
}}
[data-testid="stSidebarCollapseButton"] button {{
  color: var(--text-muted) !important;
  background: transparent !important;
  border: none !important;
}}
[data-testid="stSidebarCollapseButton"] button:hover {{
  color: var(--accent) !important;
}}
[data-testid="stSidebar"] hr,
.stApp hr {{
  border: none !important;
  border-top: 1px solid var(--border) !important;
  margin-top: 1.2rem !important;
  margin-bottom: 1.2rem !important;
  opacity: 1 !important;
}}
[data-testid="stSidebar"] [data-testid="stElementContainer"] {{
  width: 100% !important;
}}
[data-testid="stSidebar"] [data-testid="stElementContainer"]:has(.stButton) {{
  margin-top: 0px !important;
  margin-bottom: 0px !important;
  padding: 0 !important;
}}
[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] {{
  gap: 0.05rem !important;
}}
[data-testid="stSidebar"] .stButton {{
  margin-bottom: 0.02rem !important;
  margin-top: 0.02rem !important;
  width: 100% !important;
  padding: 0 !important;
}}
[data-testid="stSidebar"] .stButton > button {{
  background: transparent !important;
  border-left: 3px solid transparent !important;
  border-top: none !important;
  border-right: none !important;
  border-bottom: none !important;
  border-radius: 0 6px 6px 0 !important;
  color: var(--text-2) !important;
  font-weight: 500 !important;
  font-size: 0.9rem !important;
  text-align: left !important;
  justify-content: flex-start !important;
  width: 100% !important;
  padding: 0.25rem 0.75rem !important;
  transition: background 0.12s ease, color 0.12s ease !important;
}}
[data-testid="stSidebar"] .stButton > button > div {{
  justify-content: flex-start !important;
}}
[data-testid="stSidebar"] .stButton > button:hover {{
  background: var(--nav-hover) !important;
  color: var(--text) !important;
}}

/* Active primary button in sidebar (No Layout Shift) */
[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"],
[data-testid="stSidebar"] button[kind="primary"] {{
  background: var(--primary-light) !important;
  border-left: 3px solid var(--primary) !important;
  border-top: none !important;
  border-right: none !important;
  border-bottom: none !important;
  border-radius: 0 6px 6px 0 !important;
  color: var(--text) !important;
  font-weight: 700 !important;
}}

/* ── General Text Contrast & Labels ───────────────────── */
label[data-testid="stWidgetLabel"] p,
div[data-testid="stWidgetLabel"] p {{
  color: var(--text) !important;
}}
div[data-testid="stMarkdownContainer"] > p {{
  color: var(--text-2) !important;
}}
div[data-testid="stAlert"] p,
div[data-testid="stInfo"] p,
div[data-testid="stWarning"] p,
div[data-testid="stNotification"] p {{
  color: var(--empty-text) !important;
}}
div[data-testid="stMarkdownContainer"] h1,
div[data-testid="stMarkdownContainer"] h2,
div[data-testid="stMarkdownContainer"] h3,
div[data-testid="stMarkdownContainer"] h4,
div[data-testid="stMarkdownContainer"] h5,
div[data-testid="stMarkdownContainer"] h6 {{
  color: var(--text) !important;
}}

/* ── KPI cards ─────────────────────────────────────────── */
.kpi {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 12px 14px;
  box-shadow: var(--shadow);
}}
.kpi .label {{
  font-size: 0.72rem;
  font-weight: 700;
  color: var(--text-2);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 4px;
}}
.kpi .value {{
  font-size: 1.7rem;
  font-weight: 800;
  color: var(--text);
  line-height: 1;
}}
.kpi .sub {{
  font-size: 0.78rem;
  color: var(--text-muted);
  margin-top: 2px;
}}

/* ── Verdict badges ────────────────────────────────────── */
.badge {{
  display: inline-flex;
  align-items: center;
  padding: 0.2rem 0.65rem;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 700;
  white-space: nowrap;
}}
/* Phishing = RED (semantic danger) */
.badge-phishing {{ background: #FEF2F2; border: 1px solid #FECACA; color: #DC2626; }}
/* Spam = AMBER */
.badge-spam     {{ background: var(--warning-bg); border: 1px solid var(--warning-border); color: var(--warning); }}
/* Legitimate / Safe = GREEN */
.badge-safe     {{ background: #ECFDF5; border: 1px solid #A7F3D0; color: #059669; }}
.badge-ok      {{ background: #ECFDF5; border: 1px solid #A7F3D0; color: #059669; }}
.badge-danger  {{ background: #FEF2F2; border: 1px solid #FECACA; color: #DC2626; }}
.badge-warn    {{ background: var(--warning-bg); border: 1px solid var(--warning-border); color: var(--warning); }}

/* Dark mode badge overrides */
@media (prefers-color-scheme: dark) {{
  .badge-phishing {{ background: #450A0A; border-color: #7F1D1D; color: #F87171; }}
  .badge-safe, .badge-ok {{ background: #022C22; border-color: #064E3B; color: #34D399; }}
  .badge-danger {{ background: #450A0A; border-color: #7F1D1D; color: #F87171; }}
}}
[data-theme="dark"] .badge-phishing {{ background: #450A0A; border-color: #7F1D1D; color: #F87171; }}
[data-theme="dark"] .badge-safe,
[data-theme="dark"] .badge-ok {{ background: #022C22; border-color: #064E3B; color: #34D399; }}
[data-theme="dark"] .badge-danger {{ background: #450A0A; border-color: #7F1D1D; color: #F87171; }}

/* ── Email card (Smail) ────────────────────────────────── */
.email-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 14px;
  margin-bottom: 6px;
}}
.email-card:hover {{ border-color: var(--primary); }}
.email-card .ec-sender {{ font-size: 0.78rem; color: var(--text-2); margin-bottom: 1px; }}
.email-card .ec-subject {{ font-size: 0.95rem; font-weight: 700; color: var(--text); }}
.email-card .ec-snippet {{ font-size: 0.82rem; color: var(--text-muted); margin-top: 3px; }}

/* ── Result card (Playground) ──────────────────────────── */
.result-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px;
  box-shadow: var(--shadow);
}}
.result-phishing {{ border-top: 4px solid var(--accent); }}
.result-spam     {{ border-top: 4px solid var(--warning); }}
.result-safe     {{ border-top: 4px solid var(--safe); }}

/* ── Threat log cards ──────────────────────────────────── */
.threat-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-left: 4px solid var(--accent);
  border-radius: 0 10px 10px 0;
  padding: 12px 14px;
  margin-bottom: 6px;
}}
.threat-card .tc-subject {{ font-size: 0.95rem; font-weight: 700; color: var(--text); }}
.threat-card .tc-meta {{ font-size: 0.78rem; color: var(--text-2); }}

/* ── Generic content card ──────────────────────────────── */
.card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px 16px;
  margin-bottom: 8px;
  box-shadow: var(--shadow);
}}
.card p {{ margin: 0; }}

/* ── Login form ────────────────────────────────────────── */
.login-wrap {{
  max-width: 420px;
  margin: 3.5rem auto 0 auto;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 1.8rem 2rem;
  box-shadow: 0 4px 24px rgba(0,0,0,0.06);
  text-align: center;
}}

/* ── Misc ──────────────────────────────────────────────── */
.small {{ font-size: 0.84rem; color: var(--text-2); }}
.muted {{ font-size: 0.78rem; color: var(--text-muted); }}
.block {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px 16px;
}}
.status-dot {{
  display: inline-block;
  width: 8px; height: 8px;
  border-radius: 50%;
  vertical-align: middle;
  margin-right: 6px;
}}
.dot-green {{ background: #10B981; }}
.dot-red   {{ background: #EF4444; }}
.dot-grey  {{ background: var(--text-muted); }}

/* ── Inference status inline ──────────────────────────── */
.inference-status {{
  display: flex;
  align-items: center;
  padding: 0 0.75rem;
  font-size: 0.82rem;
  color: var(--text-2);
  gap: 0;
  margin-bottom: 1.5rem !important;
}}
.inference-status .status-label {{
  font-weight: 600;
  margin-right: 0.35rem;
}}
.inference-status .status-value {{
  color: var(--text-muted);
  font-weight: 400;
}}

/* ── Password eye icon & form hints ───────────────────── */
/* Password eye icon & form hints (improve contrast) */
button[kind="icon"],
button[kind="icon"] *,
button[aria-label*="password"],
button[aria-label*="password"] *,
[data-testid="stPasswordInput"] button,
[data-testid="stPasswordInput"] button * {{
  color: var(--text-2) !important;
}}
button[kind="icon"] svg,
button[kind="icon"] svg path,
button[aria-label*="password"] svg,
button[aria-label*="password"] svg path,
[data-testid="stPasswordInput"] button svg,
[data-testid="stPasswordInput"] button svg path {{
  fill: var(--text-2) !important;
  stroke: var(--text-2) !important;
  color: var(--text-2) !important;
}}
button[aria-label*="password"]:hover svg,
button[aria-label*="password"]:hover svg *,
[data-testid="stPasswordInput"] button:hover svg,
[data-testid="stPasswordInput"] button:hover svg * {{
    fill: var(--accent) !important;
    stroke: var(--accent) !important;
    color: var(--accent) !important;
}}

/* ── Expander toggle text contrast ────────────────────── */
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary * {{
  color: var(--text-2) !important;
  background-color: transparent !important;
}}
[data-testid="stExpander"] summary:hover,
[data-testid="stExpander"] summary:hover * {{
  color: var(--accent) !important;
}}
[data-testid="stExpander"] [data-testid="stExpanderDetails"],
[data-testid="stExpander"] [data-testid="stExpanderDetails"] *,
[data-testid="stExpander"] p,
[data-testid="stExpander"] li,
[data-testid="stExpander"] span {{
  color: var(--text) !important;
  background-color: transparent !important;
}}
.threat-expander-content p,
.threat-expander-content span,
.threat-expander-content li {{
  color: var(--text) !important;
  background-color: transparent !important;
}}

/* ── Semantic button: Phishing report (red) ───────────── */
div[data-testid="stElementContainer"]:has(.semantic-btn-danger) + div[data-testid="stElementContainer"] button {{
  background-color: #FEF2F2 !important;
  border: 1px solid #FECACA !important;
  color: #DC2626 !important;
  font-weight: 600 !important;
  border-radius: 8px !important;
  transition: all 0.15s ease !important;
}}
div[data-testid="stElementContainer"]:has(.semantic-btn-danger) + div[data-testid="stElementContainer"] button *,
div[data-testid="stElementContainer"]:has(.semantic-btn-danger) + div[data-testid="stElementContainer"] button:hover * {{
  color: inherit !important;
}}
div[data-testid="stElementContainer"]:has(.semantic-btn-danger) + div[data-testid="stElementContainer"] button:hover {{
  background-color: #DC2626 !important;
  border-color: #DC2626 !important;
  color: #FFFFFF !important;
}}
@media (prefers-color-scheme: dark) {{
  div[data-testid="stElementContainer"]:has(.semantic-btn-danger) + div[data-testid="stElementContainer"] button {{
    background-color: #450A0A !important;
    border-color: #7F1D1D !important;
    color: #F87171 !important;
  }}
  div[data-testid="stElementContainer"]:has(.semantic-btn-danger) + div[data-testid="stElementContainer"] button:hover {{
    background-color: #DC2626 !important;
    border-color: #DC2626 !important;
    color: #FFFFFF !important;
  }}
}}
[data-theme="dark"] div[data-testid="stElementContainer"]:has(.semantic-btn-danger) + div[data-testid="stElementContainer"] button {{
  background-color: #450A0A !important;
  border-color: #7F1D1D !important;
  color: #F87171 !important;
}}
[data-theme="dark"] div[data-testid="stElementContainer"]:has(.semantic-btn-danger) + div[data-testid="stElementContainer"] button:hover {{
  background-color: #DC2626 !important;
  border-color: #DC2626 !important;
  color: #FFFFFF !important;
}}

/* ── Semantic button: Safe / false positive (green) ───── */
div[data-testid="stElementContainer"]:has(.semantic-btn-safe) + div[data-testid="stElementContainer"] button {{
  background-color: #ECFDF5 !important;
  border: 1px solid #A7F3D0 !important;
  color: #059669 !important;
  font-weight: 600 !important;
  border-radius: 8px !important;
  transition: all 0.15s ease !important;
}}
div[data-testid="stElementContainer"]:has(.semantic-btn-safe) + div[data-testid="stElementContainer"] button *,
div[data-testid="stElementContainer"]:has(.semantic-btn-safe) + div[data-testid="stElementContainer"] button:hover * {{
  color: inherit !important;
}}
div[data-testid="stElementContainer"]:has(.semantic-btn-safe) + div[data-testid="stElementContainer"] button:hover {{
  background-color: #059669 !important;
  border-color: #059669 !important;
  color: #FFFFFF !important;
}}
@media (prefers-color-scheme: dark) {{
  div[data-testid="stElementContainer"]:has(.semantic-btn-safe) + div[data-testid="stElementContainer"] button {{
    background-color: #022C22 !important;
    border-color: #064E3B !important;
    color: #34D399 !important;
  }}
  div[data-testid="stElementContainer"]:has(.semantic-btn-safe) + div[data-testid="stElementContainer"] button:hover {{
    background-color: #059669 !important;
    border-color: #059669 !important;
    color: #FFFFFF !important;
  }}
}}
[data-theme="dark"] div[data-testid="stElementContainer"]:has(.semantic-btn-safe) + div[data-testid="stElementContainer"] button {{
  background-color: #022C22 !important;
  border-color: #064E3B !important;
  color: #34D399 !important;
}}
[data-theme="dark"] div[data-testid="stElementContainer"]:has(.semantic-btn-safe) + div[data-testid="stElementContainer"] button:hover {{
  background-color: #059669 !important;
  border-color: #059669 !important;
  color: #FFFFFF !important;
}}

/* ── Dropdown select icon amber ───────────────────────── */
[data-baseweb="select"] svg {{
  fill: var(--accent) !important;
  color: var(--accent) !important;
}}

/* ── Sidebar flex bottom push ─────────────────────────── */
.sidebar-spacer {{
  flex-grow: 1 !important;
  min-height: 2rem !important;
}}

/* ── Login page center fix ────────────────────────────── */
.login-logo-center {{
  display: flex !important;
  justify-content: center !important;
  align-items: center !important;
  width: 100% !important;
}}

/* ── Final overrides to ensure icon/nav/spinner contrast ── */
[data-testid="stPasswordInput"] button svg,
[data-testid="stPasswordInput"] button svg path,
[data-testid="stPasswordInput"] button svg * {{
    fill: var(--text-2) !important;
    stroke: var(--text-2) !important;
    color: var(--text-2) !important;
}}
[data-testid="stPasswordInput"] button:hover svg,
[data-testid="stPasswordInput"] button:hover svg * {{
    fill: var(--accent) !important;
    stroke: var(--accent) !important;
    color: var(--accent) !important;
}}

/* Sidebar: ensure active/hover uses readable text */
[data-testid="stSidebar"] .stButton > button:hover,
[data-testid="stSidebar"] .stButton > button:focus,
[data-testid="stSidebar"] .stButton > button:active,
[data-testid="stSidebar"] .stButton > button:hover *,
[data-testid="stSidebar"] .stButton > button:focus *,
[data-testid="stSidebar"] .stButton > button:active * {{
    color: var(--text) !important;
    background: var(--nav-hover) !important;
}}
[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"],
[data-testid="stSidebar"] button[kind="primary"],
[data-testid="stSidebar"] button[data-testid="stBaseButton-primary"] *,
[data-testid="stSidebar"] button[kind="primary"] * {{
    color: var(--text) !important;
}}

/* Spinner / status text contrast */
[data-testid="stStatus"],
[data-testid="stStatus"] *,
[role="status"],
[role="status"] * {{
    background-color: var(--surface) !important;
    color: var(--text) !important;
}}
[data-testid="stStatus"] code,
[data-testid="stStatus"] pre,
[data-testid="stStatus"] .stCodeBlock,
[role="status"] code,
[role="status"] pre,
[role="status"] .stCodeBlock {{
    background-color: var(--bg) !important;
    color: var(--text) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
}}
[data-testid="stSpinner"],
[data-testid="stSpinner"] *,
.stSpinner, .stSpinner * {{
    color: var(--text) !important;
    background-color: transparent !important;
}}

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
    if db_url := os.environ.get("SICURRE_DATA_PLATFORM_DATABASE_URL"):
        if db_url.startswith("sqlite+aiosqlite://"):
            db_url = db_url.replace("sqlite+aiosqlite://", "sqlite://", 1)
        elif db_url.startswith("postgresql+asyncpg://"):
            db_url = db_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
        return create_engine(db_url, future=True)
    return create_engine(f"sqlite:///{POC_DATA_DB_PATH}", future=True)


def _data_q(query: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    retries = 4
    wait_s = 0.2
    for attempt in range(retries):
        try:
            with _data_engine().connect() as conn:
                if _data_engine().dialect.name == "sqlite":
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
    try:
        return bool(inspect(_data_engine()).has_table(table_name))
    except Exception:
        return False


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
            "explanation": "Simulation locale : tentative de phishing probable.",
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
            "explanation": "Simulation locale : contenu promotionnel détecté.",
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
            "explanation": "Simulation locale : e-mail légitime.",
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
        full_output = "".join(output_lines)
        placeholder.code(full_output, language="bash")
        if code == 0:
            status.update(label=tr("pipeline_done"), state="complete")
            return True, full_output
        status.update(label=f"{tr('pipeline_failed')} ({code})", state="error")
        return False, full_output


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
        if center:
            st.markdown(
                f'<div style="display: flex !important; justify-content: center !important; align-items: center !important; width: 100% !important; margin: 0.5rem 0 !important; text-align: center !important;">'
                f'<img src="data:image/svg+xml;base64,{b64}" width="{width}" style="display: block !important; margin: 0 auto !important; max-width: 100% !important;" />'
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="logo-container" style="display: flex !important; align-items: center !important; justify-content: flex-start !important; margin: 0 !important; padding: 0 !important;">'
                f'<img src="data:image/svg+xml;base64,{b64}" width="{width}" style="max-width: 100% !important; margin: 0 !important;" />'
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
                    "range": ["#10B981", "#F59E0B", "#D97706"],
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
        st.markdown("<div style='margin-top: 1.5rem;'></div>", unsafe_allow_html=True)
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

    c1, c2, c3 = st.columns([1, 1.2, 1])
    with c2:
        st.markdown("<div style='margin-top: 2.5rem;'></div>", unsafe_allow_html=True)
        # Force logo centering with explicit CSS class wrapper
        if LOGO_PATH.exists():
            b64 = base64.b64encode(LOGO_PATH.read_bytes()).decode()
            st.markdown(
                f'<div class="login-logo-center">'
                f'<img src="data:image/svg+xml;base64,{b64}" width="120" style="display: block !important; max-width: 100% !important;" />'
                f"</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<div class='login-logo-center'><span style='font-size:1.6rem;font-weight:900;'>SICURRE</span></div>",
                unsafe_allow_html=True,
            )
        st.markdown("<div style='margin-top: 1.2rem;'></div>", unsafe_allow_html=True)
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
            if auth_result := authenticate_user(email, password):
                _set_user_session(auth_result)
                _auth_exec(
                    "UPDATE poc_user SET last_login_at = ? WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(), auth_result["id"]),
                )
                if remember:
                    sid = _persist_session(auth_result["id"])
                    st.query_params["sid"] = sid
                st.rerun()
            else:
                st.warning("⚠️ " + tr("invalid_credentials"))

        st.markdown("</div>", unsafe_allow_html=True)
    st.stop()


user: dict[str, Any] = st.session_state["user"]

# ── Sidebar ─────────────────────────────────────────────────────────────────
with st.sidebar:
    # Render the logo and welcome message in a single markdown block with custom margins for proper spacing
    if LOGO_PATH.exists():
        b64 = base64.b64encode(LOGO_PATH.read_bytes()).decode()
        logo_html = f'<img src="data:image/svg+xml;base64,{b64}" width="100" style="max-width: 100% !important; margin: 0 !important; display: block;" />'
    else:
        logo_html = '<span style="font-size:1.4rem;font-weight:900;letter-spacing:-1px;">SICURRE</span>'

    st.markdown(
        f"<div style='margin-top: -1.5rem; margin-bottom: 1.2rem;'>"
        f"  <div class='logo-container' style='margin-bottom: 1rem;'>{logo_html}</div>"
        f"  <div style='font-size:0.82rem;color:var(--text-2);margin-top:0.5rem;margin-bottom:0.1rem;'>{tr('welcome')}</div>"
        f"  <div style='font-weight:700;font-size:1.05rem;color:var(--text);'>{user['display_name']}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Spacing and dividing line 1 (logo area vs nav list)
    st.markdown(
        "<hr style='margin: 0.8rem 0 1.2rem 0 !important; border: none !important; border-top: 1px solid var(--border-line) !important; opacity: 1 !important;' />",
        unsafe_allow_html=True,
    )

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
        is_active = nav_key == current_page
        btn_type = "primary" if is_active else "secondary"
        if (
            st.button(
                tr(nav_key),
                key=f"_nav_{nav_key}",
                type=btn_type,
                use_container_width=True,
            )
            and not is_active
        ):
            st.session_state["page"] = nav_key
            st.rerun()

    # Flex spacer pushes bottom section down
    st.markdown("<div class='sidebar-spacer'></div>", unsafe_allow_html=True)

    # Spacing and dividing line 2 (nav list vs lower portion)
    st.markdown(
        "<hr style='margin: 0.8rem 0 !important; border: none !important; border-top: 1px solid var(--border-line) !important; opacity: 1 !important;' />",
        unsafe_allow_html=True,
    )

    # Inference status — inline on one line
    ok, status_text = inference_status()
    dot_cls = "dot-green" if ok else "dot-red"
    st.markdown(
        f"<div class='inference-status'>"
        f"<span class='status-dot {dot_cls}'></span>"
        f"<span class='status-label'>{tr('inference_status')} :</span>"
        f"<span class='status-value'>{status_text}</span>"
        f"</div>",
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
    blocked = sum(_eff_verdict(e) == "phishing" for e in events)
    delivered = sum(_eff_verdict(e) == "safe" for e in events)
    spam_safe = sum(
        _eff_verdict(e) == "safe" and _eff_label(e) == "spam" for e in events
    )

    if eval_events := [e for e in events if e.get("expected_label")]:
        fp_block = sum(
            _eff_verdict(e) == "phishing" and e.get("expected_label") != "phishing"
            for e in eval_events
        )
        fn_miss = sum(
            _eff_verdict(e) != "phishing" and e.get("expected_label") == "phishing"
            for e in eval_events
        )
        label_acc = (
            sum(_eff_label(e) == e["expected_label"] for e in eval_events)
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
        f"<div class='value' style='color:var(--danger-semantic);'>{_fmt_num(blocked)}</div></div>",
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
        # Semantic red button for phishing report
        st.markdown("<div class='semantic-btn-danger'>", unsafe_allow_html=True)
        if st.button(
            tr("flag_false_negative"),
            key=f"fn_{tab_key}_{ev['id']}",
        ):
            reclassify_event(ev["id"], "phishing", user["email"])
            st.toast(tr("reclassified_done"), icon="✅")
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

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
            if event.get("override_verdict") == "phishing":
                corr_note = f" &nbsp;<span class='badge badge-phishing'>{tr('corrected_label')}</span>"
            elif event.get("override_verdict"):
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
                    "<div class='threat-expander-content' style='font-size:0.9rem; margin: 0;'>"
                    f"<p style='margin: 0 !important;'>{snip}</p>"
                    "</div>",
                    unsafe_allow_html=True,
                )
                # Semantic green button for marking safe
                st.markdown("<div class='semantic-btn-safe'>", unsafe_allow_html=True)
                if st.button(tr("reclassify_safe"), key=f"fp_{event['id']}"):
                    reclassify_event(event["id"], "safe", user["email"])
                    st.toast(tr("reclassified_done"), icon="✅")
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

# ── Playground ────────────────────────────────────────────────────────────────
elif page == "nav_playground":
    st.title(tr("playground_title"))
    st.caption(tr("playground_subtitle"))

    # Config options at the top of the page (spanning full width)
    st.markdown("<div style='margin-bottom:8px;'></div>", unsafe_allow_html=True)
    c_llm, c_vt = st.columns(2)
    with c_llm:
        use_llm = st.checkbox(tr("enable_llm"), value=True, key="pg_use_llm")
    with c_vt:
        use_vt = st.checkbox(tr("enable_vt"), value=True, key="pg_use_vt")

    st.markdown("---")

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

        st.markdown("<div style='margin-bottom:12px;'></div>", unsafe_allow_html=True)

        if st.button(
            tr("analyze_email"),
            type="primary",
            use_container_width=True,
            key="pg_analyze_preset",
        ):
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
                result = classify_email(m_subject, m_sender, m_body, use_llm, use_vt)
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
        st.markdown(f"#### {tr('inference_result')}")
        st.markdown("<div style='margin-top: 0.5rem;'></div>", unsafe_allow_html=True)
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
        if st.button(
            tr("pipeline_base"), disabled=busy, use_container_width=True, type="primary"
        ):
            st.session_state["_pipeline_pending"] = (
                tr("pipeline_base"),
                "make poc-replay-frozen",
            )
    with b2:
        if st.button(
            tr("pipeline_cron"), disabled=busy, use_container_width=True, type="primary"
        ):
            st.session_state["_pipeline_pending"] = (
                tr("pipeline_cron"),
                "make run-pipeline",
            )
    with b3:
        if st.button(
            tr("pipeline_push"), disabled=busy, use_container_width=True, type="primary"
        ):
            st.session_state["_pipeline_pending"] = (
                tr("pipeline_push"),
                "make pipeline-push",
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


# ── Jeux de données ───────────────────────────────────────────────────────────
elif page == "nav_datasets":
    st.title(tr("data_platform_title"))
    st.caption(tr("data_platform_subtitle"))

    # Top-level volume stats
    raw_count = 0
    norm_count = 0
    dataset_item_count = 0
    if _data_table_exists("data_raw_record"):
        rows_raw = _data_q("SELECT COUNT(*) AS cnt FROM data_raw_record")
        raw_count = int(rows_raw[0]["cnt"]) if rows_raw else 0
    if _data_table_exists("data_normalized_message"):
        rows_norm = _data_q("SELECT COUNT(*) AS cnt FROM data_normalized_message")
        norm_count = int(rows_norm[0]["cnt"]) if rows_norm else 0
    if _data_table_exists("data_dataset_item"):
        rows_items = _data_q("SELECT COUNT(*) AS cnt FROM data_dataset_item")
        dataset_item_count = int(rows_items[0]["cnt"]) if rows_items else 0

    m1, m2, m3 = st.columns(3)
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
    m3.markdown(
        f"<div class='kpi'><div class='label'>{tr('total_dataset_items')}</div>"
        f"<div class='value'>{_fmt_num(dataset_item_count)}</div></div>",
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
                "scraping": "#EC4899",
                "sql": "#10B981",
                "bigdata": "#8B5CF6",
                "manual": "#F97316",
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

    st.write(
        f"**Informations du profil**"
        if st.session_state.get("lang", "fr") == "fr"
        else "**Profile Information**"
    )

    with st.form("settings_form"):
        new_name = st.text_input(tr("display_name"), value=user["display_name"])
        st.text_input(tr("email"), value=user["email"], disabled=True)
        st.text_input(
            "Rôle" if st.session_state.get("lang", "fr") == "fr" else "Role",
            value=user["role"].capitalize(),
            disabled=True,
        )
        saved = st.form_submit_button(
            tr("save_settings"), type="primary", use_container_width=True
        )

    if saved:
        name_trimmed = (new_name or "").strip()
        if name_trimmed and name_trimmed != user["display_name"]:
            _auth_exec(
                "UPDATE poc_user SET display_name = ? WHERE id = ?",
                (name_trimmed, user["id"]),
            )
            st.session_state["user"]["display_name"] = name_trimmed
            st.toast(tr("settings_saved"), icon="✅")
            st.rerun()

    # Spacing and Divider
    st.markdown(
        "<hr style='margin: 1.8rem 0 !important; border: none !important; border-top: 1px solid var(--border-line) !important; opacity: 1 !important;' />",
        unsafe_allow_html=True,
    )

    st.write(f"**{tr('preferences_title')}**")

    # Row 1: Language Selection
    col_l1, col_r1 = st.columns([3, 1])
    with col_l1:
        st.markdown(
            f"<div style='margin-top: 8px; font-weight: 600;'>{tr('application_language')}</div>"
            f"<div style='font-size: 0.85rem; color: var(--text-muted);'>{tr('application_language_desc')}</div>",
            unsafe_allow_html=True,
        )
    with col_r1:
        lang_opts = [("fr", "Français 🇫🇷"), ("en", "English 🇬🇧")]
        cur_lang_idx = 0 if st.session_state.get("lang", "fr") == "fr" else 1
        new_lang = st.selectbox(
            "Langue / Language",
            options=lang_opts,
            index=cur_lang_idx,
            format_func=lambda x: x[1],
            key="settings_lang_selector",
            label_visibility="collapsed",
        )
        if new_lang[0] != st.session_state.get("lang"):
            _set_lang(new_lang[0])
            st.rerun()

    # Divider line between toggles
    st.markdown(
        "<hr style='margin: 0.8rem 0 !important; border: none !important; border-top: 1px solid var(--border-line) !important; opacity: 1 !important;' />",
        unsafe_allow_html=True,
    )

    # Row 2: Theme Selection
    col_l2, col_r2 = st.columns([3, 1])
    with col_l2:
        st.markdown(
            f"<div style='margin-top: 8px; font-weight: 600;'>{tr('application_theme')}</div>"
            f"<div style='font-size: 0.85rem; color: var(--text-muted);'>{tr('application_theme_desc')}</div>",
            unsafe_allow_html=True,
        )
    with col_r2:
        theme_opts = [
            ("System", "🌓 System"),
            ("Light", "☀️ Light"),
            ("Dark", "🌙 Dark"),
        ]
        cur_theme = st.session_state.get("theme_mode", "System")
        theme_idx = 0
        for idx, (val, name) in enumerate(theme_opts):
            if val == cur_theme:
                theme_idx = idx
                break
        new_theme = st.selectbox(
            "Theme",
            options=theme_opts,
            index=theme_idx,
            format_func=lambda x: x[1],
            key="settings_theme_selector",
            label_visibility="collapsed",
        )
        if new_theme[0] != st.session_state.get("theme_mode"):
            st.session_state["theme_mode"] = new_theme[0]
            st.rerun()
