# Accessibility

The target is WCAG 2.1 level AA. This document records what was verified, how,
and what is not yet met — measured on 3 September 2026 against the palette in
`docs/brand/DESIGN.md` and the components in `src/app/`.

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
already accounts for it: `DESIGN.md` directs clickable text to `#2E6BB5`.
That instruction is load-bearing rather than stylistic — following it is what
keeps link text at AA — so it is recorded here as a constraint, not a
preference.

## Acceptance criteria

Applied to interface work. Each is checkable by a reviewer without tooling.

1. **Contrast.** Text uses a palette entry that passes 4.5:1 on its own
   background, or 3:1 where it is large text. `#4A90D9` is not used for body
   text on a light surface.
2. **Focus.** Every interactive element has a visible keyboard focus indicator
   (WCAG 2.4.7). The codebase uses `ring-2 ring-primary`; focus must not be
   removed without a replacement.
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
