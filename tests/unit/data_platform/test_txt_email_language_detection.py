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
    _parse_email_block,
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


def test_undetectable_text_yields_none_not_an_exception() -> None:
    """langdetect raises on text with no linguistic features.

    A raised LangDetectException here would abort ingestion of the whole file
    on one junk block, so the detector swallows it and returns None. None means
    "not selected for normalization", which is the safe outcome: an
    undetectable record must not be assumed French.
    """
    assert _detect_language("======== ==== ==== 12345 6789 !!!! ???? ....") is None


def test_text_shorter_than_the_sample_floor_is_not_guessed() -> None:
    """Short strings make langdetect unstable, so they are not classified.

    "Merci" is French, but three words is not enough signal to distinguish it
    from several other languages, and a wrong guess of "fr" is worse than None:
    it puts the record into a French-only corpus.
    """
    assert _detect_language("Merci") is None
    assert _detect_language("") is None


def test_a_parsed_block_carries_its_detected_language_through() -> None:
    """The record the parser emits is what sets detected_language downstream."""
    record = _parse_email_block(
        "Subject: Offre speciale reservee\n"
        "----------------------------------------------------------------\n"
        f"{FRENCH}\n",
        "spam_2",
    )

    assert record is not None
    assert record.language == "fr"
    assert record.label == "spam"
    assert record.source == "spam_2"


def test_an_empty_block_produces_no_record() -> None:
    assert _parse_email_block("   \n\n   ", "spam_2") is None


def test_the_fallback_record_also_detects_language() -> None:
    """A file with no recognizable block markers still yields a record.

    This is a separate construction site from _parse_email_block, so it needs
    its own detection call - hardcoding None here would reintroduce the exact
    bug for every file that fails block parsing.
    """
    from data_platform.base_ingest.file.parsers.txt_email_ingestion import _fallback_record

    record = _fallback_record(FRENCH, "spam_4")

    assert record is not None
    assert record.language == "fr"
    assert record.label == "spam"

    assert _fallback_record("   ", "spam_4") is None
