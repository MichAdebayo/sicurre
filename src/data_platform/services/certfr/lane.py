"""Run the CERT-FR chain end to end: CTI records in, generation bundle out.

Five CERT-FR services exist and every one is unit-tested, but only the router
(``CertFRStageTwoService``) had a caller. ``stage_two`` correctly marks CTI
records ``specialized_processing`` with a subtype - ``threat_intel``,
``synthetic_lure_candidate``, ``procedural_notification`` - and those subtypes
are the hand-off contract to the other four. Nothing performed the hand-off, so
88 ANSSI records routed to a destination that was never reached, against a
corpus holding 7 real phishing samples.

The unit tests could not catch this by construction: they instantiate each
service directly and assert it behaves, which says nothing about whether the
sequence is ever run.

This module is the missing sequence, and only that. It composes existing
services and emits the same bundle contract the adapted and Common Crawl lanes
already produce, so downstream review and persistence are untouched:

    raw CTI  ->  stage_two.review        (route + derived payload)
             ->  build_summary           (aggregate themes and IOCs)
             ->  build_inputs            (synthesis inputs)
             ->  build_drafts            (French phishing drafts)
             ->  build_stage_payload     (staged for human review)
             ->  generation bundle       (existing contract)

Promotion gating is left to the persistence layer, which already offers
``persist_generation_bundle_with_gated_promotion``. That matters for CERT-FR
more than for any other source: it is the most valuable phishing signal in the
platform, and machine-written lures derived from it are indistinguishable from
real ones once mixed into the corpus.

Note that ``build_summary`` consumes only the ``threat_intel`` and
``procedural_notification`` rules. A record routed to
``synthetic_lure_candidate`` contributes nothing downstream, which is easy to
miss when testing with hand-written text - a CTI report needs its report
markers (ANSSI, TLP:CLEAR, "panorama de la cybermenace") in the first 800
characters to route as threat intelligence at all.
"""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from data_platform.services.certfr.generated_drafts import CertFRGeneratedDraftService
from data_platform.services.certfr.review_staging import CertFRReviewStagingService
from data_platform.services.certfr.signal_summary import CertFRSignalSummaryService
from data_platform.services.certfr.stage_two import CertFRStageTwoService
from data_platform.services.certfr.synthesis_inputs import CertFRSynthesisInputService
from data_platform.services.shared.generation_staging import GenerationStagingService

CERTFR_SOURCE = "cert-fr-cti"
GENERATOR_NAME = "certfr_lure_generator"

#: Subtypes stage_two can emit. Kept explicit so a new one added to the router
#: without a consumer here is visible rather than silently dropped.
CONSUMED_SUBTYPES: tuple[str, ...] = (
    "threat_intel",
    "synthetic_lure_candidate",
    "procedural_notification",
)


def build_signal_bank(
    records: list[dict[str, Any]],
    *,
    cleaner=None,
) -> dict[str, Any]:
    """Group routed CTI records into the signal-bank shape build_summary expects.

    ``records`` are dicts with ``raw_record_id`` and ``raw_content``. Each is put
    through the same router the normalization pipeline uses, so the lane and the
    pipeline cannot disagree about how a record is classified.
    """
    rules: dict[str, list[dict[str, Any]]] = {key: [] for key in CONSUMED_SUBTYPES}

    for record in records:
        raw_content = record.get("raw_content") or {}
        text = str(raw_content.get("text") or "")
        if cleaner is not None:
            text = cleaner(text)
        if not text.strip():
            continue

        result = CertFRStageTwoService.review(text, raw_content)
        subtype = result.route_subtype
        if subtype not in rules:
            # Unknown subtype: keep it visible rather than discarding silently.
            rules.setdefault(subtype or "unclassified", [])
        rules.setdefault(subtype or "unclassified", []).append(
            {
                "raw_record_id": str(record.get("raw_record_id") or ""),
                "normalized_preview": result.extracted_text[:400],
                "derived_payload": result.derived_payload,
            }
        )

    return {
        "sources": [
            {
                "source_name": CERTFR_SOURCE,
                "rules": [
                    {
                        "key": key,
                        "current_count": len(samples),
                        "sampled_records": samples,
                    }
                    for key, samples in rules.items()
                ],
            }
        ]
    }


def build_certfr_generation_bundle(
    records: list[dict[str, Any]],
    *,
    run_timestamp: str | None = None,
    cleaner=None,
) -> dict[str, Any]:
    """Produce a review-staged generation bundle from CERT-FR CTI records."""
    signal_bank = build_signal_bank(records, cleaner=cleaner)
    summary = CertFRSignalSummaryService.build_summary(signal_bank)
    synthesis = CertFRSynthesisInputService.build_inputs(summary)
    drafts = CertFRGeneratedDraftService.build_drafts(synthesis)
    staged = CertFRReviewStagingService.build_stage_payload(drafts)

    samples: list[dict[str, Any]] = []
    for index, draft in enumerate(staged.get("drafts", drafts.get("drafts", []) or [])):
        # The draft builder already composes "Objet : <subject>\n\n<body>" into
        # full_text, which is the shape the training corpus uses. Rebuilding it
        # here would be a second definition of the same format, free to drift.
        normalized_text = str(draft.get("full_text") or "").strip()
        if not normalized_text:
            continue
        samples.append(
            {
                "draft_id": str(draft.get("draft_id") or f"certfr:{index}"),
                "scenario_id": str(draft.get("scenario_id") or "certfr"),
                "variant_index": int(draft.get("variant_index") or 0),
                "source_name": CERTFR_SOURCE,
                "parent_source": CERTFR_SOURCE,
                "target_label": "phishing",
                "primary_theme": str(draft.get("primary_theme") or ""),
                # The draft builder's own quality checks decide this, including
                # its duplicate-downgrade pass; it is not overridden here. Human
                # gating is a persistence concern - see
                # persist_generation_bundle_with_gated_promotion - so forcing a
                # state here would discard the builder's judgement and duplicate
                # a control that already exists downstream.
                "review_state": str(draft.get("review_state") or "pending_review"),
                "review_notes": list(draft.get("review_notes") or []),
                "text_sha256": sha256(normalized_text.encode("utf-8")).hexdigest(),
                "normalized_text": normalized_text,
                "language": "fr",
            }
        )

    return GenerationStagingService.build_bundle(
        generator_name=GENERATOR_NAME,
        source_name=CERTFR_SOURCE,
        parent_source=CERTFR_SOURCE,
        reference_selection_mode="certfr_signal_synthesis",
        input_artifact_uri=None,
        generated_artifact_uri=None,
        generated_at=run_timestamp,
        samples=samples,
    )


def summarise(bundle: dict[str, Any]) -> str:
    """One-line description for logs."""
    samples = bundle.get("samples", []) or []
    return json.dumps(
        {"generator": GENERATOR_NAME, "samples": len(samples)}, sort_keys=True
    )
