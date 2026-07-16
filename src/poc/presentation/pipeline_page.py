"""Pipeline evidence controls for the local certification POC."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

import streamlit as st

from poc.config import PocSettings
from poc.pipeline import stream_operation

MAX_TERMINAL_LINES = 200


def redact_terminal_line(line: str) -> str:
    """Redact common secret assignments from demonstration output."""
    return re.sub(
        r"(?i)\b(api[_-]?key|token|password|secret)\s*[=:]\s*\S+",
        lambda match: f"{match.group(1)}=[REDACTED]",
        line,
    )


def _stream_pipeline(
    operation_key: str, translate: Callable[[str], str], settings: PocSettings
) -> tuple[bool, str]:
    """Stream bounded allowlisted output into the local evidence terminal."""
    output_lines: list[str] = []
    with st.status(translate("pipeline_running"), expanded=True) as status:
        placeholder = st.empty()
        try:
            for line in stream_operation(operation_key, settings):
                output_lines.append(f"{redact_terminal_line(line)}\n")
                output_lines = output_lines[-MAX_TERMINAL_LINES:]
                placeholder.code("".join(output_lines[-40:]), language="bash")
        except (KeyError, PermissionError, RuntimeError) as error:
            output_lines.append(f"ERREUR: {error}\n")
            status.update(label=translate("pipeline_failed"), state="error")
            success = False
        except Exception as error:
            output_lines.append(f"ERREUR: opération interrompue ({type(error).__name__}).\n")
            status.update(label=translate("pipeline_failed"), state="error")
            success = False
        else:
            status.update(label=translate("pipeline_done"), state="complete")
            success = True
        output = "".join(output_lines)
        placeholder.code(output[-12000:], language="bash")
        return success, output


def execute_pipeline_action(
    title: str,
    operation_key: str,
    translate: Callable[[str], str],
    settings: PocSettings,
) -> None:
    """Execute one fixed pipeline action while maintaining stable UI state."""
    if st.session_state.get("pipeline_busy", False):
        st.warning(translate("pipeline_busy"))
        return
    st.session_state["pipeline_busy"] = True
    try:
        with st.spinner(f"{title}..."):
            success, output = _stream_pipeline(operation_key, translate, settings)
        st.session_state["last_pipeline_output"] = output
        st.session_state["last_pipeline_success"] = success
    finally:
        st.session_state["pipeline_busy"] = False


def render_pipeline_page(
    user: dict[str, Any],
    translate: Callable[[str], str],
    run_action: Callable[[str, str], None],
) -> None:
    """Render allowlisted pipeline evidence controls for administrators."""
    if user["role"] != "admin":
        st.warning("⚠️ " + translate("admin_only"))
        st.stop()

    st.title(translate("pipeline_title"))
    st.caption(translate("pipeline_subtitle"))
    busy = bool(st.session_state.get("pipeline_busy", False))
    if busy:
        st.warning(translate("pipeline_busy"))

    actions = (
        ("pipeline_base", "base_replay"),
        ("pipeline_cron", "incremental_demo"),
        ("pipeline_push", "release_preview"),
    )
    for column, (translation_key, operation) in zip(st.columns(3), actions, strict=True):
        with column:
            if st.button(
                translate(translation_key),
                disabled=busy,
                use_container_width=True,
                type="primary",
            ):
                st.session_state["_pipeline_pending"] = (
                    translate(translation_key),
                    operation,
                )

    if pending := st.session_state.pop("_pipeline_pending", None):
        title, operation = pending
        run_action(title, operation)

    if "last_pipeline_success" not in st.session_state:
        return
    if st.session_state["last_pipeline_success"]:
        st.info("✅ " + translate("pipeline_last_success"))
    else:
        st.warning("⚠️ " + translate("pipeline_last_error"))
