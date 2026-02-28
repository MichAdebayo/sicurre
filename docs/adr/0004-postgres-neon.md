# ADR-0004: Neon PostgreSQL (prod) + SQLite (dev)

**Date:** 2026-02-28  
**Status:** Accepted — supersedes original "Supabase" decision  

## Context
Need relational storage for audit logs, user settings, OAuth tokens, feedback, and model versions.
The original plan used Supabase-hosted PostgreSQL, but after choosing **Better Auth** for authentication (ADR-0008), Supabase's platform features (Auth, Realtime, Edge Functions) are no longer needed. Keeping Supabase only for its Postgres hosting adds unnecessary coupling and cost.

## Decision
- **Production:** Neon serverless PostgreSQL (free tier generous, autoscaling, branching for staging/preview environments).
- **Development / CI:** SQLite via compatible ORM layer (SQLAlchemy / SQLModel with dialect abstraction).

## Alternatives considered
| Option | Pros | Cons |
|--------|------|------|
| Supabase Postgres | Admin UI, integrated auth | Auth now handled by Better Auth; vendor lock-in on platform features we don't use |
| Firestore | Serverless, Google-native | Document model poor fit for relational audit queries |
| PlanetScale | MySQL-compatible, branching | MySQL dialect; less PostgreSQL ecosystem tooling |
| Self-hosted Postgres (Cloud SQL) | Full control | Higher ops burden for solo dev at MVP stage |

## Consequences
- Neon provides branching (staging = branch of prod data), instant provisioning, and scale-to-zero billing.
- SQLite in dev means zero-config local setup: `uv run` and go.
- ORM abstraction (SQLAlchemy) ensures the same Python models work against both backends.
- Migration path to Cloud SQL or any managed Postgres is trivial — standard `pg_dump`.
