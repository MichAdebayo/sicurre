# Full App Build Plan

## Purpose

This document records the build plan and current gap map for the production application in `src/app`.

The Streamlit POC remains useful for Simplon/demo evidence, but the React application is now the implemented product surface and should be treated as current runtime work, not a future branch.

## Branch boundary

- **POC surface (`src/poc`)**
  - Streamlit UI
  - local auth DB for demo users
  - local data-platform DB for demo ingestion
  - local inference service for the jury narrative
- **Production app surface (`src/app`)**
  - React 19 + TypeScript frontend
  - Better Auth integration
  - Cloudflare Email Routing integration
  - production app API wiring
  - production inference API wiring
  - deployment-grade UI, monitoring, and release setup

Do not port POC UI patterns directly into the production app. Use the POC for evidence and demos; use `src/app` for product UX.

## Non-negotiable references

Read these before writing any full-app UI or integration code:

1. [docs/brand/brand-identity.md](docs/brand/brand-identity.md)
2. [docs/architecture/component-design.md](docs/architecture/component-design.md)
3. [docs/api/openapi.yaml](docs/api/openapi.yaml)
4. [.vscode/skills/frontend-agent/SKILL.md](.vscode/skills/frontend-agent/SKILL.md)
5. [.github/copilot-instructions.md](.github/copilot-instructions.md)

## Product target

The full app should feel like a calm French SaaS product for auto-entrepreneurs, not like an AI demo.

Core product surfaces:

1. **Protection overview**
   - inbox protection status
   - weekly trend summary
   - latest actions taken
2. **Threat center**
   - searchable threat journal
   - verdict details
   - remediation and restore actions
3. **Settings and integrations**
   - Cloudflare Email Routing connection state
   - protection preferences
   - notification settings
4. **Operations and evidence**
   - ingestion and model status
   - audit trail
   - dataset / monitoring views for internal users

## Recommended stack

- **Framework**: React 19 + TypeScript
- **Routing**: React Router v7
- **Styling**: Tailwind CSS v4 with CSS variables from the brand system
- **Components**: shadcn/ui on top of Radix primitives
- **Icons**: Lucide React
- **Forms**: React Hook Form + Zod
- **Server state**: TanStack Query v5
- **Motion**: Framer Motion with the timing limits from the brand doc
- **Auth**: Better Auth sidecar or REST proxy, matching ADR-0008

## Repos and libraries to build from

These are reference systems, not branding models to imitate blindly.

### 1. Vercel Chatbot

- Repo: https://github.com/vercel/chatbot
- Use for:
  - application shell composition
  - sidebar and detail-panel patterns
  - authenticated app structure
  - production-grade layout discipline
  - pragmatic Next/React patterns for AI-adjacent products
- Do **not** copy the AI aesthetic. Borrow interaction structure, not visual theater.

### 2. shadcn/ui

- Site: https://ui.shadcn.com/
- Use for:
  - base component primitives
  - card, table, dialog, form, sheet, tabs, command menu patterns
  - a maintainable local component library copied into the repo

### 3. Radix UI

- Site: https://www.radix-ui.com/
- Use for:
  - accessibility-safe primitives
  - popovers, menus, dialogs, tabs, toggles, and overlays

### 4. Lucide

- Site: https://lucide.dev/
- Use for:
  - consistent iconography
  - light visual language that fits the Sicurre brand

## What not to copy

- No chatbot-first layout as the default product metaphor
- No fake streaming text
- No glowing AI visuals
- No third-party brand-led styling
- No “powered by AI” labels in user-facing screens

## Build phases

## Phase 1 — Foundation

- establish the React app shell
- install and configure Tailwind v4
- create CSS token mapping from the Sicurre brand doc
- set up shadcn/ui and Lucide
- create page layout primitives, empty states, loading states, and error states

Exit criteria:

- the app boots locally
- the design tokens are applied globally
- navigation, auth layout, and protected routes are in place

## Phase 2 — Authentication and user context

- integrate Better Auth sidecar with the app shell
- implement session-aware navigation
- define admin vs end-user views
- add a local dev auth harness if needed for feature development

Exit criteria:

- sign-in and sign-out work
- protected routes work
- role-aware navigation works

## Phase 3 — Protection overview and threat center

- build the dashboard overview page
- build the threat journal with filters and detail panel
- expose status actions and false-negative/false-positive feedback in the UI
- display confidence and evidence in a calm, explainable way

Exit criteria:

- a real authenticated user can review threats and understand actions taken
- the UI reads as a product, not a demo

## Phase 4 — Settings and integrations

- Cloudflare Email Routing connection flow
- account preferences
- notification preferences
- protection and remediation defaults

Exit criteria:

- the integration state is visible and understandable
- settings changes are persisted through the app API

## Phase 5 — Inference integration

- connect the production app to the production inference API
- surface inference failures clearly
- define fallback behavior explicitly in the UI and logs
- never silently downgrade behavior without user-visible status

Exit criteria:

- the application can classify via the production inference API
- auth, timeout, retry, and error states are handled predictably

## Phase 6 — Operations and monitoring surfaces

- add internal-only monitoring views when needed
- expose app health, auditability, and operational evidence
- connect frontend telemetry and product diagnostics

Exit criteria:

- internal operators can inspect runtime health without raw terminal access

## API and integration rules

- the frontend calls APIs only
- no direct database access from the frontend
- no Cloudflare or classifier calls directly from the frontend
- all Cloudflare operations go through the app API
- all contracts must follow [docs/api/openapi.yaml](docs/api/openapi.yaml)

## UX rules for the full app

- French-first copy
- whitespace over density
- restrained information hierarchy; use cards only for repeated items, framed tools, and dialogs
- confidence shown in clear language, not ML jargon
- explain actions taken in plain French
- favor calm, legible states over cleverness

## Migration path from the POC

Keep these learnings from the POC:

- separate auth data from data-platform data
- separate local demo inference from production inference
- keep operations explainable in sequence
- keep admin and end-user views distinct

Do **not** port the Streamlit page structure directly. Rebuild the product information architecture intentionally.

## Definition of done for the full-app branch

- production auth wired
- production inference wired
- threat journal functional
- protection overview functional
- settings and integration flows functional
- tests cover the critical API paths used by the app
- monitoring and error states are visible
- UI respects Sicurre brand rules
