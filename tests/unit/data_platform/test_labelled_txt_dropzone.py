"""A dropped TXT file must contribute the class its name says.

The dropzone turns a filename into a source name, so `spam_1.txt` arrives as
source `spam_1`. The TXT parser hardcoded `label="spam"` on every record, so a
file could only ever contribute spam whatever it was called - and there were no
policies for anything but `spam_1..5`.

Dropping `legitimate_1.txt` would therefore have been ingested, labelled spam,
and left under a source with no policy: never normalized, never rejected, never
mentioned. That is the same silence that hid 281 messages for months.

Legitimate is the class the corpus is shortest of - 26.8% and static - and the
one the model actually misreads, so it needed a way in.
"""

from __future__ import annotations

import pytest

from data_platform.base_ingest.file.parsers.txt_email_ingestion import (
    _fallback_record,
    label_for_source,
)
from data_platform.services.shared.normalization_pipeline import (
    NormalizationPipeline,
    NormalizedLabel,
)

FRENCH = (
    "Bonjour, veuillez trouver ci-joint le compte rendu de la reunion de service "
    "de mardi dernier ainsi que le calendrier previsionnel du prochain trimestre."
)


@pytest.mark.parametrize(
    "source,expected",
    [
        ("spam_1", "spam"),
        ("spam_5", "spam"),
        ("phishing_1", "phishing"),
        ("legitimate_1", "legitimate"),
        ("legitimate_37", "legitimate"),
    ],
)
def test_the_filename_prefix_decides_the_label(source: str, expected: str) -> None:
    assert label_for_source(source) == expected


def test_an_unknown_prefix_still_yields_spam() -> None:
    """The five existing spam_* exports must keep behaving exactly as before."""
    assert label_for_source("mailbox_1") == "spam"
    assert label_for_source("weird") == "spam"


@pytest.mark.parametrize("source", ["spam_2", "phishing_3", "legitimate_9"])
def test_a_parsed_record_carries_that_label_through(source: str) -> None:
    record = _fallback_record(FRENCH, source)

    assert record is not None
    assert record.label == label_for_source(source)
    assert record.language == "fr"


@pytest.mark.parametrize(
    "source,expected",
    [
        ("spam_1", NormalizedLabel.SPAM),
        ("phishing_4", NormalizedLabel.PHISHING),
        ("legitimate_2", NormalizedLabel.LEGITIMATE),
    ],
)
def test_the_pipeline_maps_that_label_to_the_corpus_label(
    source: str, expected: NormalizedLabel
) -> None:
    pipeline = NormalizationPipeline(session=None)  # type: ignore[arg-type]

    payload = pipeline.extract_payload(source, {"text": FRENCH, "label": label_for_source(source)})

    assert payload.label is expected
    assert payload.text


def test_an_unrecognised_label_is_rejected_rather_than_guessed() -> None:
    """A null label is refused downstream; guessing would mislabel the corpus."""
    pipeline = NormalizationPipeline(session=None)  # type: ignore[arg-type]

    payload = pipeline.extract_payload("legitimate_1", {"text": FRENCH, "label": "unknown"})

    assert payload.label is None


@pytest.mark.parametrize("source", ["spam_1", "phishing_12", "legitimate_37"])
def test_every_dropzone_source_resolves_a_policy_whatever_its_index(source: str) -> None:
    """No index may silently have no policy.

    An enumerated range always has an edge, and a source past that edge is
    ingested and then never examined - the failure this whole area exists to
    prevent.
    """
    policy = NormalizationPipeline.get_source_policy(source)

    assert policy is not None, f"{source} has no policy and would be ignored in silence"
    assert policy.normalize_messages is True


@pytest.mark.parametrize("source", ["legitimate", "spam_x", "notasource", "spam_"])
def test_only_indexed_dropzone_names_resolve(source: str) -> None:
    """The shape has to stay narrow, or unrelated sources inherit a policy."""
    assert NormalizationPipeline.get_source_policy(source) is None


def test_a_label_disagreeing_with_its_filename_is_refused() -> None:
    """A spam_3 record claiming to be legitimate did not come from that file.

    The parser derives the label from the source name, so the two can only
    disagree if the record was hand-edited or the file renamed after ingestion.
    Trusting either side over the other would put a mislabelled row into the
    corpus without a word; a null label is rejected downstream instead.
    """
    pipeline = NormalizationPipeline(session=None)  # type: ignore[arg-type]

    for source, claimed in (
        ("spam_3", "legitimate"),
        ("legitimate_1", "phishing"),
        ("phishing_2", "spam"),
    ):
        payload = pipeline.extract_payload(source, {"text": FRENCH, "label": claimed})
        assert payload.label is None, f"{source} accepted a label of {claimed!r}"
