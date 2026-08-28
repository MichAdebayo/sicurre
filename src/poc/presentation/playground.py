"""Interactive inference demonstration page for the local POC."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

import streamlit as st

from poc.inference import InferenceMode

Translator = Callable[[str], str]


class ClassifyForUi(Protocol):
    """Classification callback used by the presentation boundary."""

    def __call__(
        self,
        subject: str,
        sender: str,
        text: str,
        use_llm: bool = True,
        use_virustotal: bool = True,
    ) -> dict[str, Any] | None: ...


class PersistInference(Protocol):
    """Persistence callback used after a successful demonstration inference."""

    def __call__(self, **evidence: Any) -> None: ...


def _run_inference(
    *,
    subject: str,
    sender: str,
    text: str,
    expected_label: str | None,
    context: str,
    user_email: str,
    use_llm: bool,
    use_virustotal: bool,
    classify: ClassifyForUi,
    persist: PersistInference,
    translate: Translator,
) -> None:
    """Classify, persist evidence, and request a stable Streamlit rerun."""
    with st.spinner(translate("analyzing")):
        result = classify(subject, sender, text, use_llm, use_virustotal)
    if result is None:
        return
    st.session_state["last_result"] = result
    st.session_state.pop("last_inference_error", None)
    persist(
        user_email=user_email,
        context=context,
        subject=subject,
        sender=sender,
        text_value=text,
        result=result,
        delivered_in_smail=result["safety_verdict"] == "safe",
        expected_label=expected_label,
    )
    st.rerun()


def render_playground(
    *,
    user_email: str,
    scenarios: list[dict[str, str]],
    translate: Translator,
    allow_simulation: bool,
    classify: ClassifyForUi,
    persist: PersistInference,
    render_result: Callable[[dict[str, Any]], None],
) -> None:
    """Render real local inference and deterministic simulation journeys."""
    title_key = "playground_title" if allow_simulation else "test_email_title"
    subtitle_key = "playground_subtitle" if allow_simulation else "test_email_subtitle"
    st.title(translate(title_key))
    st.caption(translate(subtitle_key))

    if allow_simulation:
        modes = [InferenceMode.LIVE, InferenceMode.SIMULATION]
        labels = {mode: translate(f"inference_mode_{mode.value}") for mode in modes}
        stored_mode = st.session_state.get("inference_mode", InferenceMode.LIVE.value)
        current = (
            InferenceMode(stored_mode)
            if stored_mode in {mode.value for mode in modes}
            else InferenceMode.LIVE
        )
        selected = st.segmented_control(
            translate("inference_mode"),
            options=modes,
            default=current,
            format_func=lambda option: labels[option],
            selection_mode="single",
        )
        selected = selected or current
        st.session_state["inference_mode"] = selected.value
        st.caption(translate(f"inference_mode_{selected.value}_help"))
    else:
        selected = InferenceMode.LIVE
        st.session_state["inference_mode"] = selected.value

    use_llm = False
    use_virustotal = False
    st.markdown("---")

    left, right = st.columns([1, 1])
    with left:
        st.markdown(f"#### {translate('preset_scenarios')}")
        choice = st.selectbox(translate("scenario"), [item["name"] for item in scenarios])
        sample = next(item for item in scenarios if item["name"] == choice)
        st.markdown(
            "<div class='block'>"
            "<div style='font-size:0.84rem;color:var(--text-2);margin-bottom:4px;'>"
            f"<strong>{translate('sender')}:</strong> {sample['sender']}</div>"
            "<div style='font-size:0.84rem;color:var(--text-2);margin-bottom:4px;'>"
            f"<strong>{translate('subject')}:</strong> {sample['subject']}</div>"
            "<div style='font-size:0.78rem;color:var(--text-muted);'>"
            f"{translate('expected_label')}: {sample['expected_label']}</div></div>",
            unsafe_allow_html=True,
        )
        st.markdown("<div style='margin-bottom:12px;'></div>", unsafe_allow_html=True)
        if st.button(
            translate("analyze_email"),
            type="primary",
            use_container_width=True,
            key="pg_analyze_preset",
        ):
            _run_inference(
                subject=sample["subject"],
                sender=sample["sender"],
                text=sample["text"],
                expected_label=sample["expected_label"],
                context="playground",
                user_email=user_email,
                use_llm=use_llm,
                use_virustotal=use_virustotal,
                classify=classify,
                persist=persist,
                translate=translate,
            )

        st.markdown("---")
        st.markdown(f"#### {translate('manual_test')}")
        with st.form("manual_form"):
            sender = st.text_input(translate("sender"), value="expediteur@example.com")
            subject = st.text_input(translate("subject"), value="Demande de confirmation")
            body = st.text_area(
                translate("content"),
                value="Pouvez-vous valider cette demande ?",
                height=130,
            )
            submitted = st.form_submit_button(
                translate("analyze_email"), type="primary", use_container_width=True
            )
        if submitted:
            _run_inference(
                subject=subject,
                sender=sender,
                text=body,
                expected_label=None,
                context="manual",
                user_email=user_email,
                use_llm=use_llm,
                use_virustotal=use_virustotal,
                classify=classify,
                persist=persist,
                translate=translate,
            )

    with right:
        st.markdown(f"#### {translate('inference_result')}")
        st.markdown("<div style='margin-top:0.5rem;'></div>", unsafe_allow_html=True)
        if result := st.session_state.get("last_result"):
            render_result(result)
        else:
            st.info(translate("no_result_yet"))
