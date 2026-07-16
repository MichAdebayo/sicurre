"""Language state and translations for the Streamlit POC."""

from __future__ import annotations

import json
from collections.abc import MutableMapping
from pathlib import Path
from typing import Any


class PocTranslator:
    """Resolve translated copy while keeping Streamlit state at the UI boundary."""

    def __init__(self, translations_path: Path) -> None:
        """Load translations from ``translations_path`` with a safe fallback."""
        self._translations = self._load(translations_path)

    @staticmethod
    def _load(translations_path: Path) -> dict[str, dict[str, str]]:
        if translations_path.exists():
            loaded: Any = json.loads(translations_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                return loaded
        return {"fr": {"title": "Sicurre"}, "en": {"title": "Sicurre"}}

    def initialize(
        self,
        session_state: MutableMapping[str, Any],
        query_params: MutableMapping[str, Any],
    ) -> None:
        """Initialize the session language from the URL when it is not set."""
        if "lang" in session_state:
            return
        requested = query_params.get("lang", "fr")
        if isinstance(requested, list):
            requested = requested[0] if requested else "fr"
        session_state["lang"] = "en" if str(requested).lower() == "en" else "fr"

    def translate(self, key: str, language: str) -> str:
        """Return translated copy, falling back to French and then the key."""
        return self._translations.get(language, {}).get(
            key, self._translations.get("fr", {}).get(key, key)
        )

    @staticmethod
    def set_language(
        language: str,
        session_state: MutableMapping[str, Any],
        query_params: MutableMapping[str, Any],
    ) -> None:
        """Persist the selected language in session and URL state."""
        normalized = "en" if language == "en" else "fr"
        session_state["lang"] = normalized
        query_params["lang"] = normalized
