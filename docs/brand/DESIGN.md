---
name: Sicurre Product Design System
register: product
colors:
  primary: "#4A90D9"
  primary-dark: "#2E6BB5"
  primary-light: "#EAF4FF"
  secondary-amber: "#F59E0B"
  secondary-amber-dark: "#B45309"
  danger: "#EF4444"
  danger-bg: "#FEF2F2"
  safe: "#047857"
  safe-bg: "#ECFDF5"
  warning: "#B45309"
  warning-bg: "#FFFBEB"
  bg: "#F8FAFC"
  surface: "#FFFFFF"
  surface-low: "#F1F5F9"
  border: "#E2E8F0"
  text-primary: "#0F172A"
  text-secondary: "#475569"
  dark-bg: "#07111F"
  dark-surface: "#0B1626"
  dark-surface-low: "#111C2D"
  dark-border: "#26364F"
  dark-text-primary: "#F8FAFC"
  dark-text-secondary: "#B7C4D7"
typography:
  sans: "Inter, system-ui, sans-serif"
  display: "Sora, Inter, system-ui, sans-serif"
  mono: "JetBrains Mono, monospace"
rounded:
  controls: "0.5rem"
  panels: "0.75rem"
  badges: "9999px"
---

# Sicurre Design System

This file is the implementation-facing companion to [brand-identity.md](brand-identity.md). If a token conflicts, use this rule:

1. Logo-aligned primary tokens win: `#4A90D9` (primary), `#2E6BB5` (primary dark/text), `#EAF4FF` (primary surface pale).
2. Split-complementary secondary Amber (`#F59E0B` / `#B45309`) identifies attention/warnings.
3. Semantic colors keep their meaning even when the palette evolves.
4. UI components consume semantic CSS variables from `src/app/index.css`.

## Product Register

Sicurre is a task-focused security product for French auto-entrepreneurs and TPEs. The interface should feel calm, precise, and operational. It should not look like a generic AI landing page, an enterprise SOC console, or a fake growth-stage SaaS with invented social proof.

## Runtime Surfaces

- Landing page: sincere brand surface, no fake clients, fake testimonials, or unsupported numbers.
- Auth pages: quiet and trustworthy, short French-first copy.
- In-app pages: product UI with consistent navigation, compact headings, clear empty/loading/error states, and restrained motion.

## Color Rules & 60-30-10 Budget

- **Primary Blue (`#4A90D9`)**: Used for primary actions, active navigation, links, and focus rings (`focus-visible:ring-2 focus-visible:ring-primary`). For clickable text and links, use `#2E6BB5` for WCAG AA compliance (>4.5:1 ratio).
- **Secondary Amber (`#F59E0B`)**: Attention and warnings only (spam verdicts, pending DNS, advisories). Use `#7A4700` for spam text in light mode and `#FBBF24` in dark mode so spam remains distinct from phishing. Do not use Amber as a primary action button or generic decoration.
- **Red (`#EF4444`)**: Reserved for destructive actions, phishing verdict states, and critical alerts. **Known contrast gap:** unlike Blue and Amber, Red has no darker text variant, and `text-danger` on `bg-danger-bg` measures 3.44:1 in light mode and 4.37:1 in dark — both below the 4.5:1 that WCAG 2.1 AA requires for body text, and it is used at 11px. Closing it means adding the variant the other accents already have: `#B91C1C` reaches 5.91:1 on the light danger surface and `#F87171` reaches 5.94:1 on the dark one. Measured, not yet applied.
- **Green (`#047857`)**: Reserved for safe/success states. In light mode, use `#047857` for text, icons, and solid bars; reserve `#ECFDF5` for pale background tinting.
- **Surface Budget (60-30-10)**: 60% neutral surfaces (`#F8FAFC`), 30% slate typography & hairline borders (`#0F172A`, `#E2E8F0`), 10% high-intent accents.

## Typography System Rules

- **Sora**: Used strictly for H1/H2 page titles and major hero headings with `tracking-[-0.02em]` and `text-wrap: balance`. Never used on small subheadings or generic form controls.
- **Inter**: Primary UI font for navigation, forms, buttons, body text, descriptions, and tables. High x-height ensures 12px–14px legibility.
- **JetBrains Mono**: Used for identifiers, SHA-256 content hashes, IP addresses, DMARC/SPF DNS strings, ISO timestamps, and redacted MIME payloads (`font-mono text-xs text-secondary-text`).
- Avoid all-caps section labels as repeated page scaffolding.

## Motion & Transition Rules

- Motion communicates feedback, loading, reveal, or state change (150–250 ms range).
- View Transitions API (`startViewTransition`): **intended, not implemented.** It appears nowhere in `src/app` as of 3 September 2026. Kept here as a direction rather than a description, because a design system that describes behaviour the product does not have is not a specification.
- Toasts/notifications must auto-dismiss where appropriate and remain interruptible.
- Respect `prefers-reduced-motion` for repeated or decorative movement.

## Component & Human Craft Rules

- **No Card Nesting:** Cards frame repeated records, modals, forms, and framed tools. Do not nest cards ("Box-in-a-Box").
- **No Background Color Washes:** Metrics use quiet slate background cards with compact high-contrast status dots or small pill badges.
- **Hairline Borders over Heavy Shadows:** Use 1px subtle borders (`border-border-subtle`) and ambient depth (`shadow-[0_1px_2px_rgba(0,0,0,0.04)]`) instead of heavy drop shadows.
- Empty states must explain the next useful action.
- Every destructive action needs an explicit label and a recoverable path where possible.
