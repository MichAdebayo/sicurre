"""spam_1..spam_5 carry their label in the record; the pipeline must read it.

These five sources had no policy at all, so 281 records were never examined.
Adding a policy alone is not enough: without a label arm the extracted payload
gets `label = None`, the write path rejects a null label, and the records are
selected, extracted cleanly, then silently dropped for want of a label that was
present in the raw content the whole time.
"""

from __future__ import annotations

import pytest

from data_platform.services.shared.normalization_pipeline import (
    NormalizationPipeline,
    NormalizedLabel,
)

SPAM_SOURCES = ("spam_1", "spam_2", "spam_3", "spam_4", "spam_5")


def _pipeline() -> NormalizationPipeline:
    return NormalizationPipeline(session=None)  # type: ignore[arg-type]


@pytest.mark.parametrize("source", SPAM_SOURCES)
def test_a_spam_record_extracts_with_the_spam_label(source: str) -> None:
    payload = _pipeline().extract_payload(
        source,
        {
            "text": "Gagnez un iPhone gratuit ! Cliquez ici pour reclamer votre lot.",
            "label": "spam",
        },
    )

    assert payload.label is NormalizedLabel.SPAM
    assert payload.text


@pytest.mark.parametrize("raw_label", ["ham", "legitimate", "", "SPAMMY"])
def test_a_non_spam_label_yields_no_label_rather_than_a_guess(raw_label: str) -> None:
    """Only an exact `spam` becomes SPAM.

    These exports are two-class; anything else is not a spam record and must not
    be coerced into one. A null label is rejected downstream, which is the
    correct outcome - guessing would put mislabelled rows into the corpus.
    """
    payload = _pipeline().extract_payload(
        "spam_3", {"text": "Bonjour, voici le compte rendu de la reunion.", "label": raw_label}
    )

    assert payload.label is None


def test_the_label_match_is_case_insensitive() -> None:
    payload = _pipeline().extract_payload(
        "spam_2", {"text": "Offre exceptionnelle, repondez vite pour en profiter.", "label": "SPAM"}
    )

    assert payload.label is NormalizedLabel.SPAM


def test_a_missing_label_key_does_not_raise() -> None:
    payload = _pipeline().extract_payload("spam_5", {"text": "Bonjour a tous, merci."})

    assert payload.label is None
