"""Pure formatting and display normalization helpers for the POC."""

from __future__ import annotations

import hashlib
import re
from typing import Any


def format_number(value: int | float) -> str:
    """Format a numeric value using the POC's existing precision rules."""
    if isinstance(value, float):
        return f"{value:,.2f}".replace(",", " ")
    return f"{value:,}".replace(",", " ")


def safe_text(value: str, max_len: int = 200) -> str:
    """Collapse whitespace and bound user-controlled display text."""
    clean = " ".join((value or "").split())
    return clean if len(clean) <= max_len else f"{clean[: max_len - 1]}..."


def hash_token(token: str) -> str:
    """Return a deterministic SHA-256 digest for a session token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def effective_verdict(event: dict[str, Any]) -> str:
    """Return the effective safety verdict after a user override."""
    return str(event.get("override_verdict") or event.get("safety_verdict", "safe"))


def effective_label(event: dict[str, Any]) -> str:
    """Return the original classifier label for an event."""
    return str(event.get("label_verdict", "legitimate"))


def remove_links(value: str) -> str:
    """Replace URLs with the established French safety placeholder."""
    return re.sub(r"https?://\S+", "[LIEN DÉSACTIVÉ]", value)
