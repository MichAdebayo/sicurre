"""Profile and local display preferences for the Streamlit POC."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st

from poc.runtime_preflight import RuntimeCheck


def _divider(margin: str) -> None:
    st.markdown(
        f"<hr style='margin:{margin}!important;border:none!important;"
        "border-top:1px solid var(--border-line)!important;opacity:1!important;' />",
        unsafe_allow_html=True,
    )


def render_settings(
    user: dict[str, Any],
    translate: Callable[[str], str],
    update_display_name: Callable[[str, str], None],
    set_language: Callable[[str], None],
    set_theme: Callable[[str], None],
    runtime_checks: list[RuntimeCheck],
) -> None:
    """Render profile, language, and theme controls with injected persistence."""
    st.title(translate("settings_title"))
    st.caption(translate("settings_subtitle"))
    language = st.session_state.get("lang", "fr")
    st.write("**Informations du profil**" if language == "fr" else "**Profile Information**")

    with st.form("settings_form"):
        display_name = st.text_input(translate("display_name"), value=user["display_name"])
        st.text_input(translate("email"), value=user["email"], disabled=True)
        st.text_input(
            "Rôle" if language == "fr" else "Role",
            value=user["role"].capitalize(),
            disabled=True,
        )
        saved = st.form_submit_button(
            translate("save_settings"), type="primary", use_container_width=True
        )
    normalized_name = (display_name or "").strip()
    if saved and normalized_name and normalized_name != user["display_name"]:
        update_display_name(str(user["id"]), normalized_name)
        st.session_state["user"]["display_name"] = normalized_name
        st.toast(translate("settings_saved"), icon="✅")
        st.rerun()

    _divider("1.8rem 0 ")
    st.write(f"**{translate('preferences_title')}**")
    label_column, control_column = st.columns([3, 1])
    with label_column:
        st.markdown(
            f"<div style='margin-top:8px;font-weight:600;'>"
            f"{translate('application_language')}</div>"
            f"<div style='font-size:0.85rem;color:var(--text-muted);'>"
            f"{translate('application_language_desc')}</div>",
            unsafe_allow_html=True,
        )
    with control_column:
        language_options = [("fr", "Français 🇫🇷"), ("en", "English 🇬🇧")]
        selected_language = st.selectbox(
            "Langue / Language",
            options=language_options,
            index=0 if language == "fr" else 1,
            format_func=lambda option: option[1],
            key="settings_lang_selector",
            label_visibility="collapsed",
        )
        if selected_language[0] != language:
            set_language(selected_language[0])
            st.rerun()

    _divider("0.8rem 0 ")
    label_column, control_column = st.columns([3, 1])
    with label_column:
        st.markdown(
            f"<div style='margin-top:8px;font-weight:600;'>"
            f"{translate('application_theme')}</div>"
            f"<div style='font-size:0.85rem;color:var(--text-muted);'>"
            f"{translate('application_theme_desc')}</div>",
            unsafe_allow_html=True,
        )
    with control_column:
        theme_options = [
            ("System", "🌓 System"),
            ("Light", "☀️ Light"),
            ("Dark", "🌙 Dark"),
        ]
        current_theme = st.session_state.get("theme_mode", "System")
        theme_index = next(
            (index for index, option in enumerate(theme_options) if option[0] == current_theme),
            0,
        )
        selected_theme = st.selectbox(
            "Theme",
            options=theme_options,
            index=theme_index,
            format_func=lambda option: option[1],
            key="settings_theme_selector",
            label_visibility="collapsed",
        )
        if selected_theme[0] != current_theme:
            set_theme(selected_theme[0])
            st.rerun()

    _divider("1.8rem 0 ")
    st.write(f"**{translate('preflight_title')}**")
    st.caption(translate("preflight_description"))
    for check in runtime_checks:
        status_key = "preflight_ready" if check.ready else "preflight_attention"
        status_class = "badge-ok" if check.ready else "badge-danger"
        st.markdown(
            "<div class='card' style='padding:9px 12px;margin-bottom:4px;'>"
            "<div style='display:flex;justify-content:space-between;align-items:center;'>"
            f"<span>{translate(check.key)}</span>"
            f"<span class='badge {status_class}'>{translate(status_key)}</span>"
            "</div></div>",
            unsafe_allow_html=True,
        )
