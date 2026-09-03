"""The documented palette must keep meeting WCAG 2.1 AA.

`docs/brand/DESIGN.md` directs clickable text to #2E6BB5 rather than the
primary #4A90D9. That reads like a style preference and is not one: the primary
blue measures 3.34:1 on white, which is below the 4.5:1 that criterion 1.4.3
requires for body text, while #2E6BB5 measures 5.40:1.

A future palette edit that "simplifies" the two blues into one would drop link
text below AA silently, because nothing about the rendered page looks wrong.
This recomputes the ratios from the hex values so the constraint fails loudly
instead.
"""

from __future__ import annotations

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


def test_primary_blue_is_below_aa_on_white() -> None:
    """The reason the design system has two blues at all.

    If this ever passes, the palette changed and the DESIGN.md instruction
    directing clickable text to #2E6BB5 may no longer be necessary — but it
    must then be revisited deliberately rather than left as folklore.
    """
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
_DANGER_TEXT_LIGHT = ("#ef4444", "#fef2f2")
_DANGER_TEXT_DARK = ("#ef4444", "#3a1215")


def test_verdict_colours_pass_aa_where_they_are_actually_used() -> None:
    for name, (fg, bg) in _REAL_PAIRINGS.items():
        assert _contrast(fg, bg) >= _AA_BODY, f"{name} fell below AA"


def test_danger_text_is_a_known_aa_failure() -> None:
    """Documents a real failure so it cannot be quietly forgotten.

    This asserts the bug, which is unusual and deliberate. The pairing is below
    AA today and the fix is a product decision about a verdict colour, not a
    documentation change. Pinning it means the day someone darkens the red,
    this test fails and points at the docs that must be updated with it —
    rather than the failure simply persisting because nothing watched it.

    When it is fixed: raise both to >= _AA_BODY and delete this test.
    #B91C1C reaches 5.91:1 on the light surface, #F87171 5.94:1 on the dark.
    """
    light = _contrast(*_DANGER_TEXT_LIGHT)
    dark = _contrast(*_DANGER_TEXT_DARK)

    assert light < _AA_BODY, (
        f"danger text now measures {light:.2f}:1 in light mode. If this was "
        f"fixed deliberately, update docs/architecture/accessibility.md and "
        f"docs/brand/*.md, then delete this test."
    )
    assert dark < _AA_BODY, (
        f"danger text now measures {dark:.2f}:1 in dark mode. Same follow-up."
    )
    # It is at least readable as large text, which is why it is a gap and not
    # an emergency.
    assert light >= _AA_LARGE
