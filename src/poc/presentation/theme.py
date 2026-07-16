"""Theme preference state for the Streamlit POC."""

from __future__ import annotations

from collections.abc import MutableMapping
from pathlib import Path
from typing import Any, Literal, cast

ThemeMode = Literal["System", "Light", "Dark"]
THEME_MODES: tuple[ThemeMode, ...] = ("System", "Light", "Dark")
THEME_OVERRIDE_MARKER = "__THEME_OVERRIDE__"


def load_theme_css(path: Path, theme_override: str = "") -> str:
    """Load the POC stylesheet and inject the selected-theme override."""
    stylesheet = path.read_text(encoding="utf-8")
    if THEME_OVERRIDE_MARKER not in stylesheet:
        raise ValueError(f"Missing theme override marker in {path.name}")
    return stylesheet.replace(THEME_OVERRIDE_MARKER, theme_override, 1)


def initialize_theme(
    session_state: MutableMapping[str, Any],
    query_params: MutableMapping[str, Any],
) -> ThemeMode:
    """Initialize and return a validated theme preference from URL state."""
    current = session_state.get("theme_mode")
    if current in THEME_MODES:
        return cast(ThemeMode, current)
    requested = query_params.get("theme", "System")
    if isinstance(requested, list):
        requested = requested[0] if requested else "System"
    theme = cast(ThemeMode, requested if requested in THEME_MODES else "System")
    session_state["theme_mode"] = theme
    return theme


def set_theme(
    theme: str,
    session_state: MutableMapping[str, Any],
    query_params: MutableMapping[str, Any],
) -> ThemeMode:
    """Persist a validated theme preference in session and URL state."""
    normalized: ThemeMode = theme if theme in THEME_MODES else "System"
    session_state["theme_mode"] = normalized
    query_params["theme"] = normalized
    return normalized
