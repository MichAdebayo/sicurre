"""Selectable fault evidence for POC administrators."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import streamlit as st

from poc.inference import FaultProbeResult, FaultScenario

SCENARIOS = (
    FaultScenario.SERVICE_UNAVAILABLE,
    FaultScenario.INVALID_BEARER,
    FaultScenario.INVALID_CONTRACT,
)


def render_resilience(
    translate: Callable[[str], str],
    inference_health: Callable[[], tuple[bool, str]],
    run_probe: Callable[[FaultScenario], FaultProbeResult],
    inject_fault: Callable[[FaultScenario], None],
    restore_fault: Callable[[], None],
    active_fault: Callable[[], FaultScenario | None],
) -> None:
    """Inject, observe, and repair one bounded local inference incident."""
    st.title(translate("resilience_title"))
    st.caption(translate("resilience_subtitle"))

    current_fault = active_fault()
    incident = st.session_state.get("resilience_incident")
    selected_index = 0
    if isinstance(incident, dict):
        selected_value = incident.get("scenario")
        selected_index = next(
            (index for index, item in enumerate(SCENARIOS) if item.value == selected_value), 0
        )
    scenario = st.selectbox(
        translate("resilience_scenario"),
        SCENARIOS,
        index=selected_index,
        format_func=lambda value: translate(f"resilience_scenario_{value.value}"),
        key="resilience_fault_scenario",
        disabled=current_fault is not None,
    )
    st.caption(translate(f"resilience_scenario_{scenario.value}_help"))

    inject_column, restore_column = st.columns(2)
    inject_requested = inject_column.button(
        translate("resilience_inject"),
        key="resilience_inject_fault",
        type="primary",
        disabled=current_fault is not None,
        use_container_width=True,
    )
    restore_requested = restore_column.button(
        translate("resilience_restore"),
        key="resilience_restore_fault",
        disabled=current_fault is None,
        use_container_width=True,
    )

    if inject_requested:
        baseline_ready, baseline_status = inference_health()
        if not baseline_ready:
            st.error(translate("resilience_baseline_failed"))
            return
        injected_at = _timestamp()
        inject_fault(scenario)
        result = run_probe(scenario)
        st.session_state["resilience_incident"] = {
            "scenario": result.scenario.value,
            "phase": "fault_active",
            "passed": result.passed,
            "expected": result.expected,
            "observed": result.observed,
            "log": [
                f"{injected_at}  {translate('resilience_log_baseline')}: {baseline_status}",
                f"{injected_at}  {translate('resilience_log_injected')}: "
                f"{translate(f'resilience_scenario_{scenario.value}')}",
                f"{_timestamp()}  {translate('resilience_log_observed')}: "
                f"{result.observed} ({translate('resilience_expected')}: {result.expected})",
            ],
        }
        st.rerun()

    if restore_requested:
        restore_fault()
        recovered, recovery_status = inference_health()
        if not isinstance(incident, dict):
            incident = {"scenario": scenario.value, "log": []}
        incident["phase"] = "recovered" if recovered else "recovery_failed"
        incident["recovered"] = recovered
        incident["recovery_status"] = recovery_status
        incident.setdefault("log", []).extend(
            [
                f"{_timestamp()}  {translate('resilience_log_repair')}",
                f"{_timestamp()}  {translate('resilience_log_recovery')}: {recovery_status}",
            ]
        )
        st.session_state["resilience_incident"] = incident
        st.rerun()

    incident = st.session_state.get("resilience_incident")
    if not isinstance(incident, dict):
        st.info(translate("resilience_no_incident"))
        return
    phase = str(incident.get("phase"))
    if phase == "fault_active" and bool(incident.get("passed")):
        st.warning(translate("resilience_fault_confirmed"))
    elif phase == "recovered" and bool(incident.get("recovered")):
        st.success(translate("resilience_recovered"))
    else:
        st.error(translate("resilience_probe_failed"))
    st.markdown(f"#### {translate('resilience_evidence_title')}")
    st.code("\n".join(str(line) for line in incident.get("log", [])), language="text")
    st.caption(translate("resilience_scope"))


def _timestamp() -> str:
    """Return a concise local timestamp for demonstration evidence."""
    return datetime.now().strftime("%H:%M:%S")
