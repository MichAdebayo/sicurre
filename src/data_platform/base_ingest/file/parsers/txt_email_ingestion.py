"""TXT email ingestion — parses multi-email plain-text files exported from Gmail.

File format (4 files: Spam_1.txt … Spam_4.txt):

    ···From: Sender Name <email@domain.com>
    ·····To: recipient@domain.com
    ···Date: M/D/YYYY H:MM:SS AM/PM
    Subject: subject line here
    ----------------------------------------------------------------
    body line 1
    body line 2
    …

    ···From: Next email
    …

(· represents a space; records are separated by a ``   From:`` line that
begins a new block.  The header/body boundary is the first ``---`` separator
line.)

The label comes from the filename prefix, not from the content: ``spam_1.txt``
contributes spam, ``legitimate_1.txt`` contributes legitimate, ``phishing_1.txt``
contributes phishing.  See ``TXT_SOURCE_LABELS``.  An unrecognised prefix falls
back to ``"spam"``, which is what the original four Spam_*.txt exports relied
on.  The persisted text combines the subject and body.

Returns a plain list of parsed records; the caller owns DB persistence.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from langdetect import LangDetectException, detect

logger = logging.getLogger(__name__)

# Matches the "---…---" separator line that divides headers from body.
_SEPARATOR_RE = re.compile(r"^-{3,}")

# Matches the start of a new email record.  Pattern: exactly 3 leading spaces
# before "From:".
_FROM_BOUNDARY_RE = re.compile(r"(?:^|\n)   From:")


@dataclass(frozen=True, slots=True)
class TxtEmailRecord:
    text: str  # "Subject: …\n\n<body>"
    label: str  # always "spam" for these files
    source: str  # file stem, e.g. "spam_1"
    language: str | None


#: Dropzone filename prefix -> corpus label.
#:
#: The dropzone turns a filename into a source name
#: (``entry.filename.rsplit(".", 1)[0].lower()``), so ``spam_1.txt`` arrives as
#: source ``spam_1``. The label used to be hardcoded to "spam" here, which meant
#: a file could only ever contribute spam no matter what it was called - and a
#: ``legitimate_1.txt`` would have been ingested, labelled spam, and then sat
#: under a source with no normalization policy: never examined, never rejected.
#:
#: Legitimate is the class the corpus is shortest of (26.8% and static) and the
#: one the model actually misreads, so it needs a way in.
TXT_SOURCE_LABELS: dict[str, str] = {
    "spam": "spam",
    "phishing": "phishing",
    "legitimate": "legitimate",
}


def label_for_source(source: str) -> str:
    """Corpus label for a dropzone source name, from its prefix."""
    prefix = source.split("_", 1)[0].strip().lower()
    return TXT_SOURCE_LABELS.get(prefix, "spam")


def _detect_language(text: str) -> str | None:
    """Return the ISO code for *text*, or None when it cannot be determined."""
    sample = text.strip()[:1500]
    if len(sample) < 20:
        return None
    try:
        return str(detect(sample))
    except LangDetectException:
        return None


def _parse_email_block(block: str, source: str) -> TxtEmailRecord | None:
    """Parse a single email block (everything between two ``   From:`` markers).

    Returns ``None`` if the block has no usable content.
    """
    lines = block.splitlines()
    subject = ""
    body_lines: list[str] = []
    in_body = False

    for line in lines:
        if not in_body:
            if _SEPARATOR_RE.match(line):
                in_body = True
                continue
            if line.startswith("Subject:"):
                subject = line[len("Subject:") :].strip()
        else:
            body_lines.append(line)

    body = "\n".join(body_lines).strip()

    if not subject and not body:
        return None

    if subject and body:
        text = f"Subject: {subject}\n\n{body}"
    elif subject:
        text = f"Subject: {subject}"
    else:
        text = body

    return TxtEmailRecord(
        text=text,
        label=label_for_source(source),
        source=source,
        language=_detect_language(text),
    )


def _fallback_record(raw_text: str, source: str) -> TxtEmailRecord | None:
    text = raw_text.strip()
    if not text:
        return None
    return TxtEmailRecord(
        text=text,
        label=label_for_source(source),
        source=source,
        language=_detect_language(text),
    )


def _parse_txt_content(
    raw_text: str, source: str, log_context: str
) -> list[TxtEmailRecord]:
    records: list[TxtEmailRecord] = []
    blocks = re.split(r"\n(?=   From:)", raw_text)

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        record = _parse_email_block(block, source)
        if record is None:
            logger.warning("Empty/unparseable block in %s; skipping.", log_context)
            continue
        records.append(record)

    if records:
        return records

    fallback_record = _fallback_record(raw_text, source)
    if fallback_record is None:
        return []

    logger.info(
        "Falling back to single-record TXT ingestion for %s due to unsupported block structure",
        log_context,
    )
    return [fallback_record]


def parse_txt_emails(file_path: Path) -> list[TxtEmailRecord]:
    """Parse a multi-email TXT file and return one :class:`TxtEmailRecord` per email.

    Malformed or empty blocks are skipped with a warning log.
    """
    records: list[TxtEmailRecord] = []
    source = file_path.stem.lower()

    try:
        # Files use CRLF line endings (\r\n) — normalise before splitting.
        raw_text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.error("Cannot read %s: %s", file_path, exc)
        return records

    raw_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")

    records = _parse_txt_content(raw_text, source, file_path.name)

    logger.info("Parsed %d email records from %s", len(records), file_path.name)
    return records


def parse_txt_emails_from_bytes(data: bytes, source: str) -> list[TxtEmailRecord]:
    """Parse multi-email TXT content from raw bytes (R2-downloaded).

    Mirrors :func:`parse_txt_emails` but accepts bytes instead of a :class:`Path`.
    """
    raw_text = data.decode("utf-8", errors="replace")
    raw_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    records = _parse_txt_content(raw_text, source, source)

    logger.info("Parsed %d email records from bytes (%s)", len(records), source)
    return records
