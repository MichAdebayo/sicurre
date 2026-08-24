"""Selectable fault evidence for POC administrators."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import Any

import streamlit as st

from poc.inference import FaultProbeResult, FaultScenario

SCENARIOS = (
    FaultScenario.INVALID_BEARER,
    FaultScenario.INVALID_PAYLOAD,
    FaultScenario.UNREACHABLE_ENDPOINT,
)


def render_resilience(
    translate: Callable[[str], str],
    inference_health: Callable[[], tuple[bool, str]],
    run_probe: Callable[[FaultScenario], FaultProbeResult],
) -> None:
    """Exercise selectable local API failures and verify nominal recovery."""
    st.title(translate("resilience_title"))
    st.caption(translate("resilience_subtitle"))

    service_ready, service_status = inference_health()
    if service_ready:
        st.success(translate("resilience_service_ready"))
    else:
        st.error(translate("resilience_service_unavailable"))
    st.caption(service_status)

    with st.form("resilience_probe_form"):
        scenario = st.selectbox(
            translate("resilience_scenario"),
            SCENARIOS,
            format_func=lambda value: translate(f"resilience_scenario_{value.value}"),
            key="resilience_fault_scenario",
        )
        st.caption(translate(f"resilience_scenario_{scenario.value}_help"))
        submitted = st.form_submit_button(
            translate("resilience_trigger"),
            type="primary",
            disabled=not service_ready and scenario is not FaultScenario.UNREACHABLE_ENDPOINT,
        )
    if submitted:
        result = run_probe(scenario)
        recovery_ready, recovery_status = inference_health()
        st.session_state["fault_probe_result"] = {
            **asdict(result),
            "scenario": result.scenario.value,
            "recovery_ready": recovery_ready,
            "recovery_status": recovery_status,
        }

    result_data = st.session_state.get("fault_probe_result")
    if not isinstance(result_data, dict):
        st.info(translate("resilience_no_probe"))
        return
    _render_probe_result(result_data, translate)


def _render_probe_result(result: dict[str, Any], translate: Callable[[str], str]) -> None:
    """Render expected, observed, and recovery evidence for one probe."""
    passed = bool(result.get("passed"))
    recovered = bool(result.get("recovery_ready"))
    if passed and recovered:
        st.success(translate("resilience_probe_passed"))
    else:
        st.error(translate("resilience_probe_failed"))

    st.markdown(f"#### {translate('resilience_evidence_title')}")
    st.dataframe(
        [
            {
                translate("resilience_check"): translate("resilience_fault_observation"),
                translate("resilience_expected"): result.get("expected", "—"),
                translate("resilience_observed"): result.get("observed", "—"),
                translate("status"): (
                    translate("status_valid") if passed else translate("status_invalid")
                ),
            },
            {
                translate("resilience_check"): translate("resilience_recovery"),
                translate("resilience_expected"): translate("resilience_service_ready"),
                translate("resilience_observed"): result.get("recovery_status", "—"),
                translate("status"): (
                    translate("status_valid") if recovered else translate("status_invalid")
                ),
            },
        ],
        hide_index=True,
        width="stretch",
    )
    st.caption(translate("resilience_scope"))
