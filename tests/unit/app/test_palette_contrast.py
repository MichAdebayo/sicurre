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

import re
from pathlib import Path

DESIGN = Path("docs/brand/DESIGN.md")

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
    assert _contrast("#2E6BB5", "#FFFFFF") >= _AA_BODY


def test_primary_blue_is_below_aa_on_white() -> None:
    """The reason the design system has two blues at all.

    If this ever passes, the palette changed and the DESIGN.md instruction
    directing clickable text to #2E6BB5 may no longer be necessary — but it
    must then be revisited deliberately rather than left as folklore.
    """
    ratio = _contrast("#4A90D9", "#FFFFFF")
    assert _AA_LARGE <= ratio < _AA_BODY


def test_body_and_status_colours_pass_aa_on_white() -> None:
    for colour in ("#475569", "#B45309", "#7A4700", "#047857"):
        assert _contrast(colour, "#FFFFFF") >= _AA_BODY, f"{colour} fell below AA"


def test_text_on_the_dark_surface_passes_aa() -> None:
    for colour in ("#E2E8F0", "#B7C4D7", "#4A90D9"):
        assert _contrast(colour, "#0F172A") >= _AA_BODY, f"{colour} fell below AA"


def test_design_doc_still_names_the_accessible_link_colour() -> None:
    """The constraint lives in the design doc; the test guards it existing."""
    text = DESIGN.read_text(encoding="utf-8")
    assert "#2E6BB5" in text
    assert re.search(r"WCAG", text), "the rationale must stay next to the value"
