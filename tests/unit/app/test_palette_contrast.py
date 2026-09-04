"""The documented palette meets WCAG 2.1 AA."""

from __future__ import annotations

import re
from pathlib import Path

#: The palette is reproduced here rather than parsed out of
#: `docs/brand/DESIGN.md`, which is not tracked by this repository. A test that
#: reads an untracked file passes locally and fails in CI, and worse, silently
#: checks nothing wherever the file happens to be absent. These values are the
#: contract; if the design system moves away from them, this fails and someone
#: re-derives the ratios deliberately.
_LINK_BLUE = "#2E6BB5"
_PRIMARY_BLUE = "#4A90D9"
_ON_WHITE = ("#475569", "#B45309", "#7A4700", "#047857")
_ON_DARK_SURFACE = ("#E2E8F0", "#B7C4D7", "#4A90D9")
_DARK_SURFACE = "#0F172A"
_WHITE = "#FFFFFF"

#: WCAG 2.1 SC 1.4.3, verified against https://www.w3.org/TR/WCAG21/
_AA_BODY = 4.5
_AA_LARGE = 3.0


def _relative_luminance(hex_colour: str) -> float:
    raw = hex_colour.lstrip("#")
    channels = [int(raw[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(a: str, b: str) -> float:
    la, lb = _relative_luminance(a), _relative_luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def test_link_blue_passes_aa_for_body_text() -> None:
    assert _contrast(_LINK_BLUE, _WHITE) >= _AA_BODY


def test_operational_panel_token_pairs_pass_aa_in_both_themes() -> None:
    css = (Path(__file__).resolve().parents[3] / "src/app/index.css").read_text()
    light_css, dark_css = css.split("html.dark {", maxsplit=1)
    declarations = r"--color-([\w-]+):\s*(#[0-9a-fA-F]{6})\s*;"
    light = dict(re.findall(declarations, light_css))
    dark = {**light, **dict(re.findall(declarations, dark_css.split("}", 1)[0]))}
    pairs = [
        ("on-primary", "navy-dark"),
        ("on-primary-container", "primary-container"),
        ("warning", "warning-bg"),
        ("on-error-container", "error-container"),
        ("on-surface-variant", "surface-low"),
    ]
    for mode, palette in [("light", light), ("dark", dark)]:
        for foreground, background in pairs:
            ratio = _contrast(palette[foreground], palette[background])
            assert ratio >= _AA_BODY, f"{mode}: {foreground}/{background} is {ratio:.2f}:1"


def test_primary_blue_is_below_aa_on_white() -> None:
    """The reason the design system has two blues at all."""
    ratio = _contrast(_PRIMARY_BLUE, _WHITE)
    assert _AA_LARGE <= ratio < _AA_BODY


def test_body_and_status_colours_pass_aa_on_white() -> None:
    for colour in _ON_WHITE:
        assert _contrast(colour, _WHITE) >= _AA_BODY, f"{colour} fell below AA"


def test_text_on_the_dark_surface_passes_aa() -> None:
    for colour in _ON_DARK_SURFACE:
        assert _contrast(colour, _DARK_SURFACE) >= _AA_BODY, f"{colour} fell below AA"


#: Foreground/background pairs as the components actually combine them, rather
#: than each colour against a notional white. `text-danger` is never rendered on
#: white - it sits on `bg-danger-bg` - so white was the wrong thing to measure.
_REAL_PAIRINGS = {
    "safe on safe-bg (light)": ("#047857", "#ECFDF5"),
    "safe on safe-bg (dark)": ("#34d399", "#0d2c24"),
    "spam-text on warning-bg (dark)": ("#fbbf24", "#332508"),
}

#: Measured 3 September 2026. Red is the one accent with no darker text variant.
#: Danger TEXT is #b91c1c on the pale surface, #f87171 on the dark one -
#: a dedicated text token, distinct from the #ef4444 fill/border accent.
_DANGER_TEXT_LIGHT = ("#b91c1c", "#fef2f2")
_DANGER_TEXT_DARK = ("#f87171", "#3a1215")


def test_verdict_colours_pass_aa_where_they_are_actually_used() -> None:
    for name, (fg, bg) in _REAL_PAIRINGS.items():
        assert _contrast(fg, bg) >= _AA_BODY, f"{name} fell below AA"


def test_danger_text_passes_aa_on_both_danger_surfaces() -> None:
    """The Domain Shield badge failure is fixed by a dedicated text token."""
    light = _contrast(*_DANGER_TEXT_LIGHT)
    dark = _contrast(*_DANGER_TEXT_DARK)

    assert light >= _AA_BODY, f"danger text light is {light:.2f}:1, below AA"
    assert dark >= _AA_BODY, f"danger text dark is {dark:.2f}:1, below AA"
