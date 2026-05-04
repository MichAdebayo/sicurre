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

All emails in these files are spam/phishing samples — ``label`` is hardcoded
to ``"spam"``.  The persisted text combines the subject and body.

Returns a plain list of parsed records; the caller owns DB persistence.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

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

    return TxtEmailRecord(text=text, label="spam", source=source, language=None)


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

    # Split on the record-start boundary "   From:" (3-space prefix).
    # re.split with a look-ahead keeps the boundary in the subsequent segment.
    blocks = re.split(r"\n(?=   From:)", raw_text)

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        record = _parse_email_block(block, source)
        if record is None:
            logger.warning("Empty/unparseable block in %s; skipping.", file_path.name)
            continue
        records.append(record)

    logger.info("Parsed %d email records from %s", len(records), file_path.name)
    return records


def parse_txt_emails_from_bytes(data: bytes, source: str) -> list[TxtEmailRecord]:
    """Parse multi-email TXT content from raw bytes (R2-downloaded).

    Mirrors :func:`parse_txt_emails` but accepts bytes instead of a :class:`Path`.
    """
    records: list[TxtEmailRecord] = []
    raw_text = data.decode("utf-8", errors="replace")
    raw_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n(?=   From:)", raw_text)

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        record = _parse_email_block(block, source)
        if record is None:
            logger.warning("Empty/unparseable block in %s; skipping.", source)
            continue
        records.append(record)

    logger.info("Parsed %d email records from bytes (%s)", len(records), source)
    return records
