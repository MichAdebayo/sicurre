"""Selectable fault evidence for POC administrators."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from typing import Any

import streamlit as st

from poc.inference import FaultProbeResult, FaultScenario

SCENARIOS = (
    FaultScenario.SERVICE_UNAVAILABLE,
    FaultScenario.INVALID_BEARER,
    FaultScenario.INVALID_CONTRACT,
)


def render_resilience(
    translate: Callable[[str], str],
    inference_health: Callable[[], tuple[str, str]],
    run_probe: Callable[[FaultScenario], FaultProbeResult],
    run_recovery_probe: Callable[[], FaultProbeResult],
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
        baseline_state, baseline_status = inference_health()
        if baseline_state != "ready":
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
            "evidence": asdict(result),
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
        recovery_result = run_recovery_probe()
        recovery_state, recovery_status = inference_health()
        recovered = recovery_result.passed and recovery_state == "ready"
        if not isinstance(incident, dict):
            incident = {"scenario": scenario.value, "log": []}
        incident["phase"] = "recovered" if recovered else "recovery_failed"
        incident["recovered"] = recovered
        incident["recovery_status"] = recovery_status
        incident["recovery_evidence"] = asdict(recovery_result)
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
    evidence = incident.get("evidence")
    if isinstance(evidence, dict):
        st.markdown(f"##### {translate('resilience_fault_exchange_title')}")
        st.code(format_probe_evidence(evidence, translate), language="json")
    recovery_evidence = incident.get("recovery_evidence")
    if isinstance(recovery_evidence, dict):
        st.markdown(f"##### {translate('resilience_recovery_exchange_title')}")
        st.code(format_probe_evidence(recovery_evidence, translate), language="json")
    st.caption(translate("resilience_scope"))


def _timestamp() -> str:
    """Return a concise local timestamp for demonstration evidence."""
    return datetime.now().strftime("%H:%M:%S")


def format_probe_evidence(
    evidence: dict[str, Any],
    translate: Callable[[str], str],
) -> str:
    """Render one sanitized HTTP exchange and Sicurre's resulting decision."""
    detail = str(evidence.get("validation_detail") or "")
    if detail.startswith("recovery_error:"):
        detail_text = f"{translate('resilience_detail_recovery_error')} {detail.split(':', 1)[1]}"
    else:
        detail_text = translate(f"resilience_detail_{detail}") if detail else ""
    transcript = {
        translate("resilience_request"): {
            "method": evidence.get("request_method"),
            "path": evidence.get("request_path"),
            "headers": {"Authorization": "Bearer [REDACTED]"},
            "body": evidence.get("request_body"),
        },
        translate("resilience_response"): {
            "status": evidence.get("response_status"),
            "body": evidence.get("response_body"),
        },
        translate("resilience_decision"): {
            translate("resilience_validation"): translate(
                f"resilience_validation_{evidence.get('validation', 'not_evaluated')}"
            ),
            translate("resilience_detail"): detail_text,
            translate("resilience_outcome"): translate(
                f"resilience_outcome_{evidence.get('application_outcome', 'request_rejected')}"
            ),
            translate("resilience_expected"): evidence.get("expected"),
            translate("resilience_observed"): evidence.get("observed"),
        },
    }
    return json.dumps(transcript, ensure_ascii=False, indent=2)
