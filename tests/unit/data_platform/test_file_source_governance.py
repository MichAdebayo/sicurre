"""File sources must declare a legal basis, personal-data flag and retention.

Every other extractor sets these three fields when it registers its source.
File sources did not, so eleven rows carried a NULL legal basis, no retention,
and `contains_personal_data = False` — including the operator's own mailbox
exports, which hold real sender addresses and display names.

False is the wrong default for exactly the sources most likely to contain
personal data, and a default is silent: nothing fails, the row is simply
created wrong. These tests pin the classification so a new dropzone prefix
cannot quietly inherit the public-corpus defaults.
"""

from __future__ import annotations

import pytest

from data_platform.base_ingest.file.parsers.csv_ingestion import file_source_governance

REQUIRED = ("legal_basis", "contains_personal_data", "retention_days")


@pytest.mark.parametrize(
    "source",
    ["spam_1", "spam_5", "legitimate_1", "phishing_3", "SPAM_9", " legitimate_12 "],
)
def test_dropzone_exports_declare_personal_data(source: str) -> None:
    """Mailbox exports carry real senders, whatever their label prefix says."""
    governance = file_source_governance(source)

    assert governance["contains_personal_data"] is True
    assert governance["legal_basis"] == "legitimate_interest_security"
    assert governance["retention_days"] == 365


@pytest.mark.parametrize(
    "source", ["kaggle_french_spamham", "kaggle_multilingual_spam", "zefang_phishing"]
)
def test_published_corpora_are_not_personal_data(source: str) -> None:
    governance = file_source_governance(source)

    assert governance["contains_personal_data"] is False
    assert governance["legal_basis"] == "public_research_dataset"


def test_enron_is_public_and_still_personal_data() -> None:
    """Public and citable does not mean anonymous.

    Enron is a published research corpus and it is real employee mail. Declaring
    it as carrying personal data costs nothing and avoids an obvious question.
    """
    governance = file_source_governance("enron_spam")

    assert governance["legal_basis"] == "public_research_dataset"
    assert governance["contains_personal_data"] is True


@pytest.mark.parametrize(
    "source", ["spam_1", "kaggle_french_spamham", "enron_spam", "some_new_corpus"]
)
def test_every_file_source_gets_all_three_fields(source: str) -> None:
    """No source may be registered with a field left unset."""
    governance = file_source_governance(source)

    for field in REQUIRED:
        assert field in governance, f"{source} would be registered without {field}"
    assert governance["retention_days"] is not None
    assert governance["legal_basis"]
