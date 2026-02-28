# ADR-0008: Better Auth for authentication and session management

**Date:** 2026-02-28  
**Status:** Accepted  

## Context
Sicurre needs user authentication, session management, and secure storage/refresh of per-user Gmail OAuth tokens (`gmail.modify` sensitive scope).

After dropping Supabase as the database platform (ADR-0004), Supabase Auth no longer comes "for free." We need an auth solution that:

1. Supports Google OAuth with **custom scopes** (specifically `gmail.modify` — a restricted/sensitive scope requiring Google verification).
2. Gives full control over the token lifecycle — we must encrypt, store, and refresh Gmail tokens ourselves.
3. Runs self-hosted or as a library (no external SaaS dependency at runtime).
4. Demonstrates Simplon competency: "Sécuriser l'accès à la solution IA" (Bloc 3 C20).

## Decision
Use **Better Auth** — a TypeScript/framework-agnostic auth library that runs as middleware alongside our FastAPI backend (via its REST API adapter or as a sidecar service).

## Alternatives considered

| Option | Pros | Cons |
|--------|------|------|
| **Supabase Auth** | Integrated with Supabase, easy setup | Tied to Supabase platform we no longer use; limited control over custom Gmail scopes; opaque token storage |
| **Auth.js (NextAuth)** | Popular, many providers | Tightly coupled to Next.js; poor fit for FastAPI backend; limited custom scope handling |
| **Keycloak** | Enterprise-grade, full OIDC | Very heavy for solo-dev MVP; Java runtime; complex ops |
| **Firebase Auth** | Free tier, Google-native | Cannot request `gmail.modify` scope through Firebase; limited customization |
| **Custom JWT implementation** | Full control | Reinventing the wheel; high risk of security mistakes |

## Why Better Auth

- **Custom OAuth scopes:** Can request `gmail.modify` during the Google OAuth flow and capture the resulting `refresh_token`.
- **Token control:** We intercept the token callback, encrypt the refresh token (AES-256-GCM), and store it in our own `oauth_tokens` table.
- **Framework-agnostic:** Exposes a REST API — our FastAPI backend calls it or proxies its endpoints. Works with any frontend (Streamlit POC, React prod).
- **Self-hosted:** Runs in the same Cloud Run container or as a sidecar — no external auth SaaS at runtime.
- **Session management:** Built-in session table, CSRF protection, and cookie/bearer token modes.
- **Portability:** If we ever move to a different provider, our auth layer is just a library swap — no platform migration.

## Implementation outline

1. Better Auth runs as a Node.js sidecar (or embedded if we switch to a TS frontend proxy).
2. FastAPI validates sessions by calling Better Auth's session verification endpoint (or by verifying JWT tokens Better Auth issues).
3. On Google OAuth callback, custom handler encrypts `refresh_token` → writes to `oauth_tokens` table → creates session.
4. `sessions` table managed by Better Auth; `oauth_tokens` table managed by Sicurre API.

## Consequences

- **Added complexity:** One more service (Node.js sidecar) or need to bridge TS↔Python. Mitigated by Better Auth's REST API — FastAPI just makes HTTP calls.
- **Security ownership:** We own the auth stack — must handle CSRF, session expiry, token rotation ourselves. Better Auth provides primitives, but we configure them.
- **Simplon alignment:** Demonstrates full understanding of auth architecture, OAuth flows, and token security — stronger than just using a managed auth service.
