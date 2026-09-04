"""A dropped record must say why it was dropped.

Records discarded during normalization kept `rejection_reason = NULL`, so 7,226
French records sat in the database indistinguishable from records nobody had
looked at yet. The reason existed — the code branched on it — it was simply
never written down, which meant the C3 claim that failures carry an explicit
queryable reason was not true of this path.

The reasons are deterministic and recomputable from the stored raw content, so
nothing was lost permanently; but a report should not have to re-run the
pipeline to answer "why was this dropped".
"""

from __future__ import annotations

import inspect

from data_platform.services.shared.normalization_pipeline import NormalizationPipeline

EXPECTED_REASONS = (
    "empty_after_extraction",
    "no_label",
    "duplicate_text_sha256",
)


def _normalize_source() -> str:
    return inspect.getsource(NormalizationPipeline)


def test_every_drop_point_records_a_reason() -> None:
    """Each `continue` that discards a record first names the reason."""
    source = _normalize_source()

    for reason in EXPECTED_REASONS:
        assert f'rec.rejection_reason = "{reason}"' in source, (
            f"the {reason} drop path does not persist its reason"
        )
    assert 'rec.rejection_reason = f"route:{payload.route_outcome}"' in source, (
        "the routing drop path does not persist which route outcome applied"
    )


def test_no_silent_skip_remains() -> None:
    """No `skipped_count += 1` may occur without a reason being set first."""
    source = _normalize_source()
    lines = source.splitlines()

    for index, line in enumerate(lines):
        if "skipped_count += 1" not in line:
            continue
        window = "\n".join(lines[max(0, index - 4) : index])
        assert "rejection_reason" in window or "reason" in window, (
            f"line {index} increments skipped_count without recording a reason:\n{window}\n{line}"
        )
