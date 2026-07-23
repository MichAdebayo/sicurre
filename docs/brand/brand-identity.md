# Sicurre Brand Identity

Status: Active  
Last aligned with implementation: 2026-07-23

This document is the canonical brand contract. `DESIGN.md` translates it into
component rules, and `src/app/index.css` implements its tokens. When they differ,
the logo-aligned primary tokens and semantic meanings below take precedence.

## Brand Position

Sicurre is a French-first email security product for independent professionals
and small businesses. Its voice is calm, direct, transparent, and useful. It does
not claim customers, performance figures, commercial plans, legal status, or
service levels that have not been established.

## Primary & Secondary Color Tokens

Sicurre uses a split-complementary **Primary Blue + Secondary Amber** palette designed for operational clarity in security products:

- **Primary Blue (`#4A90D9`)**: Identifies brand identity, primary actions, active navigation, and focus rings (`ring-2 ring-primary`). For clickable text and inline links, use the darker variant **`#2E6BB5`** to guarantee WCAG AA contrast (>4.5:1 ratio). Primary blue is an action color, not a verdict color.
- **Secondary Amber (`#F59E0B`)**: Identifies attention required, spam verdicts, pending DNS verification, trial/quota advisories, and warning highlight banners. For text and inline warning icons, use **`#B45309`** (Amber Dark) to maintain WCAG AA contrast.

### 60-30-10 Color Budget

To prevent visual noise ("AI-generated slot-machine UI"), interfaces enforce a strict color budget:
1. **60% Dominant Neutral Surfaces:** `#F8FAFC` (light BG) / `#07111F` (dark BG).
2. **30% Structural Typography & Hairline Borders:** `#0F172A` (primary text), `#475569` (secondary text), `#E2E8F0` (subtle border).
3. **10% High-Intent Accents:** Primary Blue actions, Secondary Amber warnings, Semantic Red (`#EF4444`) phishing alerts, and Safe Green (`#047857`) legitimate verdicts.

## Semantic Verdict Colors

| Meaning | Foreground | Pale surface | Usage |
|---|---:|---:|---|
| Safe/success | `#047857` | `#ECFDF5` | Delivered, valid, completed |
| Warning / Attention | `#B45309` (fg) / `#F59E0B` (badge) | `#FFFBEB` | Spam, partial DNS, attention required |
| Danger/error | `#EF4444` | `#FEF2F2` | Phishing, failure, destructive action |

Semantic meaning must remain stable in both light and dark themes. Pale surface washes are reserved for compact status badges, never full-card background fills.

## Surfaces And Text

| Token | Light | Dark |
|---|---:|---:|
| Background | `#F8FAFC` | `#07111F` |
| Surface | `#FFFFFF` | `#0B1626` |
| Secondary surface | `#F1F5F9` | `#111C2D` |
| Border | `#E2E8F0` | `#26364F` |
| Primary text | `#0F172A` | `#F8FAFC` |
| Secondary text | `#475569` | `#B7C4D7` |

Text, controls, charts, focus states, and semantic badges target WCAG AA contrast.
Dark mode is a complete token substitution (`color-scheme: light dark`), not a filter or a collection of page-specific overrides.

## Typography System

- **Sora**: Brand headings and major page titles (H1/H2) only. Applied with tight tracking (`tracking-[-0.02em]`) and balanced wrapping (`text-wrap: balance`). Never used on small subheadings or generic controls.
- **Inter**: Primary UI text, navigation, forms, buttons, tables, descriptions, and charts. High x-height ensures 12px–14px legibility.
- **JetBrains Mono**: Technical identifiers, SHA-256 content hashes, IP addresses, DMARC/SPF DNS strings, ISO timestamps, and redacted MIME payloads (`font-mono text-xs text-secondary-text`).
- Product body text is normally 14–16 px. Essential helper text does not fall below 12 px.

## Human Craft Principles (Anti-Patterns to Avoid)

- **No Card Nesting:** Cards frame repeated records, modals, forms, and genuine tools. They are not page-section decoration and must never be nested ("Box-in-a-Box").
- **No Background Color Washes:** Metrics use quiet slate background cards with compact high-contrast status dots or small pill badges.
- **No Icon-per-Heading Fatigue:** Do not prepend Lucide icons to every heading or label. Rely on strong typographic hierarchy (`Sora` H1/H2).
- **Hairline Borders over Heavy Shadows:** Use 1px subtle borders (`border-border-subtle`) and ambient depth (`shadow-[0_1px_2px_rgba(0,0,0,0.04)]`) instead of heavy drop shadows.

## Motion And Transitions

- Product transitions stay in the 150–250 ms range and respect `prefers-reduced-motion`.
- View Transitions API (`startViewTransition`) visually connects element state changes between screens and slide-out inspection drawers.

