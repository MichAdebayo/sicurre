# ADR-0008: Better Auth for authentication and session management

**Date:** 2026-02-28  
**Status:** Accepted  

## Context
Sicurre needs user authentication, session management, workspace membership, and a clean boundary between the React app, the FastAPI backend, and integration credentials.

After dropping Supabase as the database platform (ADR-0004), Supabase Auth no longer comes "for free." We need an auth solution that:

1. Supports email/password and optional provider-based sign-in without coupling the app to a managed auth SaaS.
2. Gives full control over session persistence and user/workspace mapping.
3. Runs self-hosted or as a library (no external SaaS dependency at runtime).
4. Demonstrates Simplon competency: "Sécuriser l'accès à la solution IA" (Bloc 3 C20).

## Decision
Use **Better Auth** — a TypeScript/framework-agnostic auth library that runs as
a sidecar service beside the FastAPI backend. Keep that boundary rather than
switching the public app to Neon Auth during the current deployment pass.

Local development and container smoke tests use a dedicated SQLite Better Auth
database. Production uses the existing Neon PostgreSQL instance through a
dedicated `auth` schema and Better Auth's PostgreSQL adapter. The public
`/api/auth/*` boundary is identical in both environments; only persistence
changes.

## Alternatives considered

| Option | Pros | Cons |
|--------|------|------|
| **Supabase Auth** | Integrated with Supabase, easy setup | Tied to Supabase platform we no longer use; opaque token/session storage |
| **Auth.js (NextAuth)** | Popular, many providers | Tightly coupled to Next.js; poor fit for FastAPI backend; limited custom scope handling |
| **Keycloak** | Enterprise-grade, full OIDC | Very heavy for solo-dev MVP; Java runtime; complex ops |
| **Firebase Auth** | Free tier, Google-native | External runtime dependency; limited customization |
| **Custom JWT implementation** | Full control | Reinventing the wheel; high risk of security mistakes |
| **Neon Auth** | Managed auth endpoint; auth data branches with Neon | Newer Neon-specific runtime/API dependency; not a drop-in replacement for the current Better Auth client/sidecar contract |

## Why Better Auth

- **Sidecar boundary:** Runs as `auth-service`, a Node.js sidecar exposing `/api/auth/*` while FastAPI owns product APIs.
- **Session control:** Better Auth manages users, accounts, sessions, and verification rows in an auth-owned schema. SQLite is retained only for local/POC and container smoke use; Neon PostgreSQL is the production persistence target.
- **Framework-agnostic:** Exposes a REST API — our FastAPI backend calls it or proxies its endpoints. Works with any frontend (Streamlit POC, React prod).
- **Self-hosted:** Runs on the same application host as a sidecar — no external auth SaaS at runtime.
- **Session management:** Built-in session table, CSRF protection, and cookie/bearer token modes.
- **Portability:** If we ever move to a different provider, our auth layer is just a library swap — no platform migration.

## Implementation outline

1. Better Auth runs as a Node.js sidecar (or embedded if we switch to a TS frontend proxy).
2. FastAPI validates sessions by calling Better Auth's session verification endpoint (or by verifying JWT tokens Better Auth issues).
3. FastAPI maps the authenticated Better Auth user to `app_workspace` and `workspace_member`.
4. Better Auth manages auth tables; Sicurre API manages Cloudflare integration tokens separately.
5. Production startup uses the dedicated Neon `auth` schema so library-owned
   tables cannot collide with Sicurre domain tables. Production rejects any
   local SQLite path configuration.

## Consequences

- **Added complexity:** One more service (Node.js sidecar) or need to bridge TS↔Python. Mitigated by Better Auth's REST API — FastAPI just makes HTTP calls.
- **Security ownership:** We own the auth stack — must handle CSRF, session expiry, token rotation ourselves. Better Auth provides primitives, but we configure them.
- **Simplon alignment:** Demonstrates full understanding of auth architecture, OAuth flows, and token security — stronger than just using a managed auth service.
- **Operational trade-off:** The sidecar remains one small Node.js service, but
  avoids hard-coupling customer identity to a Neon-specific external auth
  endpoint. Neon remains the production database provider, not the auth
  provider contract.
