# Sicurre — Brand Identity

## Brand Essence

**Product:** Sicurre — French-native phishing detection for auto-entrepreneurs  
**Tagline:** *Vos emails, protégés en 2 secondes.*  
**Positioning:** Calm, trustworthy, approachable — security without the fear-mongering  

Sicurre is not an enterprise security product. It's a quiet guardian for solo professionals who don't have an IT team. The brand must feel like a **trusted French accountant** — reliable, plain-spoken, on your side.

### Three brand adjectives
**Rassurant · Simple · Français**

---

## Color Palette

### Core

| Token | Name | Hex | Usage |
|-------|------|-----|-------|
| `--color-primary` | Bleu Sicurre | `#1B4FCC` | Primary actions, links, header |
| `--color-primary-dark` | Bleu foncé | `#1239A6` | Hover states, focus rings |
| `--color-primary-light` | Bleu clair | `#EEF3FF` | Backgrounds, chips, tag fills |
| `--color-accent` | Ambre | `#F59E0B` | CTAs, highlights, onboarding steps |
| `--color-accent-dark` | Ambre foncé | `#D97706` | Accent hover |

### Semantic

| Token | Name | Hex | Usage |
|-------|------|-----|-------|
| `--color-danger` | Rouge alerte | `#EF4444` | Phishing verdict badge, error state |
| `--color-danger-bg` | Rouge pâle | `#FEF2F2` | Alert card background |
| `--color-safe` | Vert confiance | `#10B981` | Legitimate verdict badge, success |
| `--color-safe-bg` | Vert pâle | `#ECFDF5` | Safe card background |
| `--color-warning` | Jaune prudence | `#F59E0B` | Low-confidence verdicts, warnings |
| `--color-warning-bg` | Jaune pâle | `#FFFBEB` | Warning card background |

### Neutrals (Slate scale)

| Token | Hex | Usage |
|-------|-----|-------|
| `--color-bg` | `#F8FAFC` | Page background |
| `--color-surface` | `#FFFFFF` | Card / panel surface |
| `--color-border` | `#E2E8F0` | Dividers, input borders |
| `--color-text-primary` | `#0F172A` | Body text, headings |
| `--color-text-secondary` | `#475569` | Secondary labels, meta |
| `--color-text-muted` | `#94A3B8` | Placeholder, disabled |

### Dark mode (future)
Mirror the slate scale inverted. Primary `#60A5FA`. Danger `#F87171`. Keep accent `#FBBF24`.

---

## Typography

### Font stack

| Role | Font | Source | Tailwind class |
|------|------|--------|----------------|
| **UI / body** | Inter | Google Fonts / bunny.net (free) | `font-sans` |
| **Display / marketing** | Sora | Google Fonts (free) | `font-display` |
| **Code / signals / confidence scores** | JetBrains Mono | Google Fonts (free) | `font-mono` |

```css
/* tailwind.config.ts */
fontFamily: {
  sans: ['Inter', 'system-ui', 'sans-serif'],
  display: ['Sora', 'Inter', 'sans-serif'],
  mono: ['JetBrains Mono', 'monospace'],
}
```

### Type scale (Tailwind defaults — do not deviate without reason)

| Role | Class | Size |
|------|-------|------|
| Page title | `text-3xl font-display font-bold` | 1.875rem |
| Section heading | `text-xl font-semibold` | 1.25rem |
| Card title | `text-base font-semibold` | 1rem |
| Body | `text-sm` | 0.875rem |
| Meta / label | `text-xs text-muted` | 0.75rem |
| Confidence score | `text-sm font-mono` | 0.875rem |

---

## Iconography

- Library: **Lucide React** (free, tree-shakeable, consistent with shadcn/ui defaults)
- Size: `16px` inline with text, `20px` standalone buttons, `24px` section icons
- Stroke width: `1.5` (default) — do not use filled icons
- Phishing verdict icon: `ShieldAlert` (red)
- Legitimate verdict icon: `ShieldCheck` (green)
- Trash action: `Trash2`
- Restore action: `RotateCcw`
- Settings: `Settings2`

---

## Motion (Framer Motion)

Sicurre's users are anxious about phishing. Motion should **calm and confirm**, never distract.

### Rules
- Use micro-animations only. No parallax, no scroll-triggered effects.
- Duration: `150ms` for immediate feedback (button press), `250ms` for state changes, `350ms` for page/panel transitions.
- Easing: `easeOut` for elements entering, `easeIn` for leaving.
- Stagger list items by `30ms` max (threat log rows appearing).

### Approved patterns
```tsx
// Verdict badge pulse — confirms classification completed
initial={{ scale: 0.8, opacity: 0 }}
animate={{ scale: 1, opacity: 1 }}
transition={{ duration: 0.2, ease: 'easeOut' }}

// Threat log row entrance
initial={{ opacity: 0, y: 8 }}
animate={{ opacity: 1, y: 0 }}
transition={{ duration: 0.25, ease: 'easeOut' }}

// Dismiss / restore fade
exit={{ opacity: 0, x: -16 }}
transition={{ duration: 0.15, ease: 'easeIn' }}
```

### Banned patterns
- Infinite looping animations (except a single subtle pulse on "Scanning…" state)
- Bounce easing (`type: 'spring'` with high bounce)
- Any animation > 400ms on a user-triggered action

---

## Component Library

**shadcn/ui** — primary component source. All components copy-pasted into `src/components/ui/`, never imported from npm directly.

### Customisation rules
- Extend shadcn primitives; do not rewrite them.
- Apply brand colors via CSS custom properties (see palette above), not hardcoded hex in components.
- Verdict badges are custom — use `<VerdictBadge verdict="phishing" confidence={0.97} />` not raw `<Badge>`.
- Confidence scores always rendered in `font-mono`.

---

## French UI Language Rules

All user-facing text is **French by default**. English only in: code, technical logs, developer-only interfaces.

### Tone
- Use **vous** (formal) in all user-facing copy — auto-entrepreneurs expect professional tone.
- Short sentences. Active voice. No passive constructions.
- Avoid FUD (fear, uncertainty, doubt) phrasing. Instead of "ATTENTION : email dangereux", use "Email suspect détecté — déplacé dans la corbeille."

### Key string patterns
| Situation | ✅ Do | ❌ Don't |
|-----------|-------|---------|
| Phishing detected | "Email de phishing détecté" | "ALERTE : Email malveillant !!!" |
| Legitimate | "Email légitime" | "Email safe / OK" |
| Confidence score | "Confiance : 97 %" | "Score: 0.97" |
| Action taken | "Déplacé dans la corbeille" | "Trashed" |
| Restore | "Restaurer cet email" | "Undo trash" |
| Empty state | "Aucun email suspect cette semaine 🎉" | "No threats found" |
| Error | "Une erreur est survenue. Réessayez dans quelques instants." | "500 Internal Server Error" |

### Numbers and dates
- Confidence: `97 %` (space before %)
- Dates: `28 février 2026` (French locale, no ordinal)
- Currency: `5 €/mois` (symbol after amount)

---

## Inspiration References

Aesthetic direction — clean, serious but human, SaaS dashboard:
- Linear.app (clean, fast, keyboard-first)
- Vercel dashboard (minimal, monochrome surfaces)
- Alan (French health insurance app — trusted, French, approachable)
- Shine (French neo-bank for auto-entrepreneurs — exact ICP)

Key observation from Shine and Alan: French B2C SaaS that targets auto-entrepreneurs uses **plenty of whitespace**, **large readable type**, and **avoids dense data tables** in favour of card-based layouts. Follow this.

**Dribbble inspiration (start here for every new screen):**
https://dribbble.com/search/saas-dashboard-security
https://dribbble.com/search/email-security-dashboard
https://dribbble.com/search/cybersecurity-app-ui

Before implementing any new screen or component, spend 5 minutes on Dribbble using the links above. Screenshot or link the 2–3 shots that best match the intended feel and reference them in the PR description or design comment.

---

## The "No AI Aesthetic" Rule

**This is a product. Not a demonstration of AI technology.**

Sicurre happens to use AI internally — the user does not need to know or care. The UI should never:

- Display animated neural network graphs, glowing nodes, or particle effects
- Use "typing" animations to simulate AI thinking (no fake streaming text in the dashboard)
- Show robot icons, brain emojis, or circuit-board motifs
- Label any UI element with "Powered by AI", "AI-detected", or "ML confidence" — say "Confiance : 97 %" and nothing more
- Use gradient meshes, holographic glows, or neon cyberpunk palettes
- Animate a "scanning..." state with dramatic visual effects — a simple spinner or subtle pulse is enough

**The UI should be innovative and creative through:** layout elegance, motion craft, typographic clarity, and interaction precision — not through AI visual clichés.

Ask yourself before adding any visual element: *"Would Stripe, Linear, or Alan put this in their product?"* If the answer is no, remove it.
