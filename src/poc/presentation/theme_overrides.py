"""Theme CSS override strings for POC light and dark modes.

Extracted from app.py to keep the Streamlit composition shell free of
inline style blocks.  The returned CSS is injected after the base
poc.css stylesheet.
"""

from __future__ import annotations

LIGHT_OVERRIDES = """
:root {
  --bg: #F8FAFC !important;
  --surface: #FFFFFF !important;
  --border: #E2E8F0 !important;
  --border-line: #E2E8F0 !important;
  --text: #0F172A !important;
  --text-2: #475569 !important;
  --text-muted: #64748B !important;
  --cta-text: #FFFFFF !important;
  --cta-bg: #2E6BB5 !important;
  --cta-hover: #245996 !important;
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

DARK_OVERRIDES = """
:root {
  --bg: #07111F !important;
  --surface: #0B1626 !important;
  --border: #26364F !important;
  --border-line: rgba(255, 255, 255, 0.25) !important;
  --text: #F8FAFC !important;
  --text-2: #B7C4D7 !important;
  --text-muted: #8090A6 !important;
  --cta-text: #FFFFFF !important;
  --cta-bg: #2E6BB5 !important;
  --cta-hover: #3B7BC4 !important;
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

/* Forced dark: record remediation actions */
[class*="st-key-fn_"] button { background-color: #450A0A !important; border-color: #7F1D1D !important; color: #FCA5A5 !important; }
[class*="st-key-fp_"] button { background-color: #022C22 !important; border-color: #065F46 !important; color: #6EE7B7 !important; }
[class*="st-key-fn_"] button *, [class*="st-key-fp_"] button * { color: inherit !important; }

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

/* Forced dark: preserve semantic remediation fills inside expander details. */
[data-testid="stExpander"] [data-testid="stExpanderDetails"] [class*="st-key-fn_"] button {
  background-color: #450A0A !important;
  border-color: #7F1D1D !important;
  color: #FCA5A5 !important;
}
[data-testid="stExpander"] [data-testid="stExpanderDetails"] [class*="st-key-fp_"] button {
  background-color: #022C22 !important;
  border-color: #065F46 !important;
  color: #6EE7B7 !important;
}
[data-testid="stExpander"] [data-testid="stExpanderDetails"] [class*="st-key-fn_"] button:hover {
  background-color: #DC2626 !important;
  border-color: #DC2626 !important;
  color: #FFFFFF !important;
}
[data-testid="stExpander"] [data-testid="stExpanderDetails"] [class*="st-key-fp_"] button:hover {
  background-color: #047857 !important;
  border-color: #047857 !important;
  color: #FFFFFF !important;
}

/* Forced dark: collapsible sidebar button */
[data-testid="stSidebarCollapseButton"] button svg,
[data-testid="stSidebarCollapsedControl"] button svg,
[data-testid="stSidebarCollapseButton"] [data-testid="stIconMaterial"],
[data-testid="stSidebarCollapsedControl"] [data-testid="stIconMaterial"],
button[data-testid="stExpandSidebarButton"] [data-testid="stIconMaterial"] {
  fill: #FFFFFF !important;
  color: #FFFFFF !important;
}
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


def get_theme_override_css(theme_mode: str) -> str:
    """Return the CSS override string for the given theme mode.

    Args:
        theme_mode: One of "Light", "Dark", or any other value (no override).

    Returns:
        A CSS string to inject after the base poc.css stylesheet, or empty
        string if no override is needed.
    """
    if theme_mode == "Light":
        return LIGHT_OVERRIDES
    if theme_mode == "Dark":
        return DARK_OVERRIDES
    return ""
