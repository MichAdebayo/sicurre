"""Exported mailbox files must carry a detected language, not a null.

The parser hardcoded ``language=None``. That propagated through file_dropzone
into ``detected_language`` on every raw record, and the normalization query
selects on ``detected_language == "fr"`` - so those records were never selected.
Not rejected, never examined: 281 messages sat invisible that way.

Detection has to be per-record rather than a blanket value. These exports are
93.6% English, so writing "fr" across the board would push English messages into
a French-only corpus. Detected English is simply not selected for normalization
and stays available as adaptation source material.
"""

from data_platform.base_ingest.file.parsers.txt_email_ingestion import (
    _detect_language,
    parse_txt_emails_from_bytes,
)

FRENCH = (
    "Bonjour, nous vous informons que votre compte sera suspendu sous 48 heures. "
    "Merci de confirmer vos coordonnees bancaires via le portail securise."
)
ENGLISH = (
    "Dear customer, we are writing to inform you that your account will be "
    "suspended within 48 hours. Please confirm your billing details now."
)


def test_french_body_is_detected_as_french() -> None:
    assert _detect_language(FRENCH) == "fr"


def test_english_body_is_not_labelled_french() -> None:
    """The corpus is French-only; mislabelling English here silently poisons it."""
    detected = _detect_language(ENGLISH)

    assert detected != "fr"
    assert detected == "en"


def test_text_too_short_to_judge_returns_none_rather_than_guessing() -> None:
    assert _detect_language("merci") is None
    assert _detect_language("") is None


def test_parsed_records_carry_a_language_instead_of_null() -> None:
    """Regression guard: the parser used to emit language=None unconditionally."""
    block = (
        "   From: Expediteur <a@b.fr>\n"
        "     To: moi@exemple.fr\n"
        "Subject: Votre facture est disponible\n"
        "----------------------------------------------------------------\n"
        f"{FRENCH}\n"
    )

    records = parse_txt_emails_from_bytes(block.encode("utf-8"), "spam_1")

    assert records, "expected at least one parsed record"
    assert records[0].language == "fr"
    assert records[0].label == "spam"
