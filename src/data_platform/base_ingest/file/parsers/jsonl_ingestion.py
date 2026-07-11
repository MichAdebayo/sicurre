"""JSONL ingestion — parses newline-delimited JSON files with {text, label} schema.

Each line is a JSON object.  Only lines with a non-empty ``text`` field are
ingested.  The ``label`` field is used as-is (e.g. ``"spam"`` / ``"ham"``).

Returns a plain list of parsed records so the caller owns DB persistence
(no direct DB access here — single-responsibility).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

JSONL_REQUIRED_FIELDS: frozenset[str] = frozenset({"text", "label"})


@dataclass(frozen=True, slots=True)
class JsonlRecord:
    text: str
    label: str
    source: str
    language: str | None


def parse_jsonl(file_path: Path) -> list[JsonlRecord]:
    """Parse a JSONL file and return one :class:`JsonlRecord` per valid line.

    Lines that are blank, malformed JSON, or missing the ``text`` field are
    silently skipped with a warning log.
    """
    records: list[JsonlRecord] = []
    source = file_path.stem.lower()

    try:
        raw_text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("Cannot read %s: %s", file_path, exc)
        return records

    for line_no, line in enumerate(raw_text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            logger.warning(
                "Line %d in %s is not valid JSON: %s", line_no, file_path.name, exc
            )
            continue

        text = str(obj.get("text", "")).strip()
        if not text:
            logger.warning(
                "Line %d in %s has empty text; skipping.", line_no, file_path.name
            )
            continue

        label = str(obj.get("label", "")).strip()
        lang = str(obj.get("language", "")).strip() or None

        records.append(
            JsonlRecord(text=text, label=label, source=source, language=lang)
        )

    logger.info("Parsed %d records from %s", len(records), file_path.name)
    return records


def parse_jsonl_from_bytes(data: bytes, source: str) -> list[JsonlRecord]:
    """Parse JSONL content from raw bytes (R2-downloaded).

    Mirrors :func:`parse_jsonl` but accepts bytes instead of a :class:`Path`.
    """
    records: list[JsonlRecord] = []
    raw_text = data.decode("utf-8", errors="replace")

    for line_no, line in enumerate(raw_text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            logger.warning("Line %d in %s is not valid JSON: %s", line_no, source, exc)
            continue

        text = str(obj.get("text", "")).strip()
        if not text:
            logger.warning("Line %d in %s has empty text; skipping.", line_no, source)
            continue

        label = str(obj.get("label", "")).strip()
        lang = str(obj.get("language", "")).strip() or None

        records.append(
            JsonlRecord(text=text, label=label, source=source, language=lang)
        )

    logger.info("Parsed %d records from bytes (%s)", len(records), source)
    return records
