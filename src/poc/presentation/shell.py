"""Login and navigation shell for the Streamlit POC."""

from __future__ import annotations

import base64
from collections.abc import Callable
from pathlib import Path
from typing import Any

import streamlit as st

Translator = Callable[[str], str]

PERSONAL_NAVIGATION_KEYS = (
    "nav_home",
    "nav_smail",
    "nav_threat_log",
    "nav_playground",
)

ADMIN_NAVIGATION_KEYS = (
    "nav_admin",
    "nav_pipeline",
    "nav_datasets",
    "nav_resilience",
)

ADMIN_ONLY_PAGE_KEYS = frozenset(ADMIN_NAVIGATION_KEYS)


def page_is_allowed(role: str, page: str) -> bool:
    """Return whether a role may resolve the requested POC page."""
    return role == "admin" or page not in ADMIN_ONLY_PAGE_KEYS


def _render_navigation_button(
    navigation_key: str, current_page: str, translate: Translator
) -> None:
    """Render one navigation button and persist a changed selection."""
    is_active = navigation_key == current_page
    selected = st.button(
        translate(navigation_key),
        key=f"_nav_{navigation_key}",
        type="primary" if is_active else "secondary",
        use_container_width=True,
    )
    if selected and not is_active:
        st.session_state["page"] = navigation_key
        st.rerun()


def _logo_html(logo_path: Path, width: int, *, login: bool = False) -> str:
    """Build logo markup without coupling asset loading to page orchestration."""
    if not logo_path.exists():
        size = "1.6rem" if login else "1.4rem"
        return f'<span style="font-size:{size};font-weight:900;">SICURRE</span>'
    encoded = base64.b64encode(logo_path.read_bytes()).decode()
    return (
        f'<img src="data:image/svg+xml;base64,{encoded}" width="{width}" '
        'style="display:block!important;max-width:100%!important;margin:0!important;" />'
    )


def render_login(
    *,
    logo_path: Path,
    translate: Translator,
    authenticate: Callable[[str, str], dict[str, Any] | None],
    establish_session: Callable[[dict[str, Any]], None],
    record_login: Callable[[str], None],
    remember_session: Callable[[str], str],
) -> None:
    """Render the local login and stop execution until authentication succeeds."""
    _, center, _ = st.columns([1, 1.2, 1])
    with center:
        st.markdown("<div style='margin-top:0.75rem;'></div>", unsafe_allow_html=True)
        st.markdown(
            f'<div class="login-logo-center">{_logo_html(logo_path, 120, login=True)}</div>',
            unsafe_allow_html=True,
        )
        st.markdown("<div style='margin-top:1.2rem;'></div>", unsafe_allow_html=True)
        st.markdown(
            f"<h3 style='margin:0 0 4px;color:var(--text);text-align:center;'>"
            f"{translate('login_title')}</h3>",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<p style='font-size:0.88rem;color:var(--text-2);margin-bottom:1.2rem;"
            f"text-align:center;'>{translate('login_subtitle')}</p>",
            unsafe_allow_html=True,
        )
        with st.form("login_form"):
            email = st.text_input(translate("email"), placeholder="you@company.com")
            password = st.text_input(translate("password"), type="password")
            remember = st.checkbox(translate("remember_me"), value=True)
            submitted = st.form_submit_button(
                translate("sign_in"), type="primary", use_container_width=True
            )

        if submitted:
            user = authenticate(email, password)
            if user:
                establish_session(user)
                record_login(str(user["id"]))
                if remember:
                    st.query_params["sid"] = remember_session(str(user["id"]))
                st.rerun()
            else:
                st.warning("⚠️ " + translate("invalid_credentials"))
        st.markdown("</div>", unsafe_allow_html=True)
    st.stop()


def render_sidebar(
    *,
    logo_path: Path,
    user: dict[str, Any],
    translate: Translator,
    inference_health: Callable[[], tuple[str, str]],
    sign_out: Callable[[], None],
) -> None:
    """Render deterministic navigation, inference health, and sign-out controls."""
    with st.sidebar:
        st.markdown(
            "<div class='sidebar-identity'>"
            f"<div class='logo-container' style='margin-bottom:1rem;'>"
            f"{_logo_html(logo_path, 88)}</div>"
            f"<div style='font-size:0.82rem;color:var(--text-2);margin-top:0.5rem;"
            f"margin-bottom:0.1rem;'>{translate('welcome')}</div>"
            f"<div style='font-weight:700;font-size:1.05rem;color:var(--text);'>"
            f"{user['display_name']}</div></div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<hr style='margin:0.8rem 0 1.2rem!important;border:none!important;"
            "border-top:1px solid var(--border-line)!important;opacity:1!important;' />",
            unsafe_allow_html=True,
        )
        current_page = st.session_state.get("page", "nav_home")
        st.markdown(
            f"<div class='sidebar-section-label'>{translate('personal_space')}</div>",
            unsafe_allow_html=True,
        )
        for navigation_key in PERSONAL_NAVIGATION_KEYS:
            _render_navigation_button(navigation_key, current_page, translate)

        if user["role"] == "admin":
            st.markdown(
                f"<div class='sidebar-section-label admin'>{translate('administration')}</div>",
                unsafe_allow_html=True,
            )
            for navigation_key in ADMIN_NAVIGATION_KEYS:
                _render_navigation_button(navigation_key, current_page, translate)

        with st.container(key="sidebar_actions"):
            st.markdown(
                "<hr style='margin:0!important;border:none!important;"
                "border-top:1px solid var(--border-line)!important;opacity:1!important;' />",
                unsafe_allow_html=True,
            )
            settings_active = current_page == "nav_settings"
            settings_selected = st.button(
                translate("nav_settings"),
                key="_nav_nav_settings",
                type="primary" if settings_active else "secondary",
                use_container_width=True,
            )
            if settings_selected and not settings_active:
                st.session_state["page"] = "nav_settings"
                st.rerun()

            with st.container(key="sidebar_signout_group"):
                if st.button(translate("sign_out"), key="_sidebar_signout"):
                    sign_out()
                    st.rerun()

        if user["role"] == "admin":
            with st.container(key="sidebar_inference_footer"):
                status_state, status_text = inference_health()
                dot_class = {
                    "ready": "dot-green",
                    "authentication_rejected": "dot-amber",
                    "contract_invalid": "dot-amber",
                }.get(status_state, "dot-red")
                st.markdown(
                    "<div class='inference-status'><div class='status-heading'>"
                    f"<span class='status-dot {dot_class}'></span>"
                    f"<span class='status-label'>{translate('inference_status')}</span></div>"
                    f"<span class='status-value'>{status_text}</span></div>",
                    unsafe_allow_html=True,
                )
