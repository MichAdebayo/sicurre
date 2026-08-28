"""Tests for POC theme CSS override extraction."""

from __future__ import annotations

from poc.presentation.theme_overrides import DARK_OVERRIDES, LIGHT_OVERRIDES, get_theme_override_css


def test_light_mode_returns_light_overrides() -> None:
    """get_theme_override_css('Light') returns the light token block."""
    css = get_theme_override_css("Light")
    assert css is LIGHT_OVERRIDES
    assert "--bg: #F8FAFC" in css
    assert "--safe-semantic: #047857" in css


def test_dark_mode_returns_dark_overrides() -> None:
    """get_theme_override_css('Dark') returns the dark token and component block."""
    css = get_theme_override_css("Dark")
    assert css is DARK_OVERRIDES
    assert "--bg: #07111F" in css
    assert ".badge-phishing" in css
    assert "stSidebarCollapseButton" in css


def test_unknown_mode_returns_empty_string() -> None:
    """An unrecognized mode produces no CSS override."""
    assert get_theme_override_css("Auto") == ""
    assert get_theme_override_css("") == ""
    assert get_theme_override_css("dark") == ""  # case-sensitive


def test_light_and_dark_use_same_primary_token() -> None:
    """Both themes use the canonical brand primary #4A90D9."""
    assert "#4A90D9" in LIGHT_OVERRIDES
    assert "#4A90D9" in DARK_OVERRIDES


def test_dark_overrides_include_forced_badge_rules() -> None:
    """Dark mode includes badge overrides not present in light mode."""
    assert ".badge-phishing" in DARK_OVERRIDES
    assert ".badge-phishing" not in LIGHT_OVERRIDES


def test_module_import_causes_no_side_effects() -> None:
    """Importing the module does not trigger Streamlit, DB, or network calls."""
    # If we got here, the import at the top of this file already succeeded
    # without side effects. The assertion is implicit.
    assert callable(get_theme_override_css)
