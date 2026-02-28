# ADR-0004: Postgres (Supabase) for audit logs and user data

**Date:** 2026-02-28  
**Status:** Accepted  

## Context
Need relational storage for audit logs, user settings, feedback, and model versions.

## Decision
Use Supabase-hosted PostgreSQL in MVP.

## Alternatives
- Firestore: good but less ideal for relational audit queries
- SQLite: not suitable for multi-user SaaS

## Consequences
- Easy admin UI + SQL power
- Upgrade path to paid tier when needed
