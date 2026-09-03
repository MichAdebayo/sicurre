# Accessibility

The target is WCAG 2.1 level AA. This document records what was verified, how,
and what is not yet met — measured on 3 September 2026 against the design
system's palette and the components in `src/app/`.

The palette values are reproduced here rather than cited, because the brand
document that defines them is not tracked in this repository. A reference a
reader cannot follow is worse than the values themselves.

It is written as a status, not as a claim of conformance. A conformance
statement needs an audit of every page against every applicable criterion; what
follows is narrower and says so.

## Contrast — verified by calculation

Every foreground in the documented palette was run through the WCAG relative
luminance formula rather than accepted from the design document.

| Colour | On | Ratio | AA (4.5:1 body / 3:1 large) |
|---|---|---|---|
| `#2E6BB5` link blue | white | 5.40:1 | Pass, body text |
| `#4A90D9` primary blue | white | 3.34:1 | **Large text and non-text only** |
| `#475569` slate body | white | 7.58:1 | Pass |
| `#B45309` amber | white | 5.02:1 | Pass |
| `#7A4700` amber dark | white | 7.70:1 | Pass |
| `#047857` green | white | 5.48:1 | Pass |
| `#E2E8F0` light text | `#0F172A` | 14.48:1 | Pass |
| `#B7C4D7` muted text | `#0F172A` | 10.11:1 | Pass |
| `#4A90D9` primary blue | `#0F172A` | 5.34:1 | Pass |

The one value below 4.5:1 is the primary blue on white, and the design system
already accounts for it by directing clickable text to `#2E6BB5`. That
instruction is load-bearing rather than stylistic — following it is what keeps
link text at AA — so it is recorded here as a constraint rather than a
preference, and `tests/unit/app/test_palette_contrast.py` recomputes both
ratios so a palette change cannot quietly drop link text below AA.

## Acceptance criteria

Applied to interface work. Each is checkable by a reviewer without tooling.

1. **Contrast.** Text uses a palette entry that passes 4.5:1 on its own
   background, or 3:1 where it is large text. `#4A90D9` is not used for body
   text on a light surface (`#2E6BB5` is the accessible substitute), and danger
   text uses `--color-danger-text`, not the `#EF4444` fill accent.
2. **Focus.** Every interactive element has a visible keyboard focus indicator
   (WCAG 2.4.7). The codebase uses `focus-visible:ring-2` with
   `focus-visible:ring-primary`, which is the right form: the ring appears on
   keyboard focus and not on a mouse click. Where `focus-visible:outline-none`
   removes the default outline, a ring must replace it in the same rule.
3. **Names.** Every control has an accessible name — visible text, or
   `aria-label` where the control is iconographic.
4. **Images.** Every `<img>` carries `alt`; decorative images carry `alt=""`
   or `aria-hidden="true"` so a screen reader skips them rather than reading a
   filename.
5. **Status.** Asynchronous results that change without a page navigation —
   a scan verdict, a quarantine action — are announced in a live region.
6. **Keyboard.** Any flow that can be completed with a mouse can be completed
   with a keyboard, in a focus order that follows the visual order.
7. **Structure.** One `h1` per page and no skipped heading levels, so the
   document outline is navigable.

## Current state

Measured across the 39 component files in `src/app/`:

| Signal | Files |
|---|---|
| `aria-label` | 18 |
| `aria-hidden` | 11 |
| `role=` | 12 |
| `alt=` | 9 |
| `focus-visible` | 4 |
| `aria-labelledby` / `aria-describedby` | 2 each |
| `aria-live` | 1 |

Accessibility work is present and deliberate rather than incidental — the
`aria-hidden` count in particular shows decorative elements being hidden on
purpose. It is also uneven: one `aria-live` region across the application is
thin for a product whose primary output is an asynchronous verdict, and
criterion 5 above is the least well met of the seven.

## Resolved: danger text

Danger text used the `#EF4444` accent directly, which measured **3.44:1** on the
pale danger surface and 4.37:1 on the dark one — both below the 4.5:1 that
criterion 1.4.3 requires for body text, and rendered at 11px on the Domain
Shield status badge, far too small for the 3:1 large-text allowance.

Red was the only accent without a dedicated text variant: blue has `#2E6BB5`,
amber has `#7A4700`, green uses `#047857`. It now has one too. A
`--color-danger-text` token carries `#B91C1C` in light mode (**5.91:1** on the
danger surface) and `#F87171` in dark mode (**5.94:1**), and the badge uses it
in place of the raw accent.

`#EF4444` is unchanged as the danger **fill, border and icon** accent, where it
pairs with a white or dark `on-danger` foreground rather than with the tinted
background — so verdict badges keep their identity while their text becomes
legible. `test_palette_contrast.py` asserts both surfaces now pass AA; if either
regresses, restore the token rather than relaxing the test.

## What has not been done

No automated audit (axe, Lighthouse) and no screen-reader pass has been run.
The criteria above are stated so that interface work can be reviewed against
them; they are not evidence that every existing screen already satisfies them.
Stating that limit is more useful than a conformance claim the project cannot
support.

## Documents

Report accessibility is a separate requirement, addressed by the
`skills/sicurre-accessible-report` tooling: tagged PDF export, structured
headings, explicit link text and tables with headers.
