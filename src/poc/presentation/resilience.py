"""Controlled incident evidence for POC administrators."""

from __future__ import annotations

from collections.abc import Callable

import streamlit as st


def render_resilience(
    translate: Callable[[str], str],
    inference_health: Callable[[], tuple[bool, str]],
    trigger_incident: Callable[[], str],
) -> None:
    """Demonstrate one bounded inference outage and its recovery workflow."""
    st.title(translate("resilience_title"))
    st.caption(translate("resilience_subtitle"))

    incident_active = bool(st.session_state.get("controlled_incident_active", False))
    service_ready, service_status = inference_health()
    observed_ready = service_ready and not incident_active

    status_column, action_column = st.columns([2, 1])
    with status_column:
        if observed_ready:
            st.success(translate("resilience_service_ready"))
        else:
            st.error(translate("resilience_service_unavailable"))
        st.caption(service_status)
    with action_column:
        if incident_active:
            if st.button(
                translate("resilience_recover"),
                type="primary",
                use_container_width=True,
            ):
                st.session_state["controlled_incident_active"] = False
                st.rerun()
        elif st.button(
            translate("resilience_trigger"),
            type="primary",
            use_container_width=True,
        ):
            st.session_state["controlled_incident_message"] = trigger_incident()
            st.session_state["controlled_incident_active"] = True
            st.rerun()

    if incident_active:
        st.code(
            f"PocInferenceUnavailable: {st.session_state.get('controlled_incident_message', '')}",
            language="text",
        )

    st.markdown(f"#### {translate('resilience_evidence_title')}")
    evidence = (
        ("1", translate("resilience_symptom"), not observed_ready),
        ("2", translate("resilience_diagnosis"), incident_active),
        ("3", translate("resilience_recovery"), not incident_active),
        ("4", translate("resilience_validation"), observed_ready),
    )
    for number, label, complete in evidence:
        icon = "✓" if complete else "·"
        st.markdown(f"**{number}. {label}** &nbsp; {icon}")

    st.info(translate("resilience_scope"))
