# Agent Lessons

Patterns captured after corrections. Review at the start of each session.

---

## L-001 — DB access boundary (architecture invariant)

**Mistake:** Diagram showed `gmail-listener` writing directly to the DB (`ING -->|Write audit log| DB`).  
**Rule:** Only `sicurre-api` holds a DB connection. `gmail-listener` and `phishing-api` must call `sicurre-api` over HTTP to persist anything. This is checked at diagram level, not just code level.  
**Test:** Before generating any Mermaid diagram or sequence diagram, verify no arrow runs from `ING` or `CLS` to `DB` directly.

---

## L-002 — Stale brand references survive find-replace

**Mistake:** After renaming the product from InboxSentinel → Sicurre, several research docs still contained the old product name, including the competitive-analysis, tech-stack-survey, and bloc-by-bloc task list. The agent persona "Roda/Rodalega" leaked into README.md.  
**Rule:** After any product rename or brand change, run a workspace-wide grep for the old name before marking work complete.  
**Test:** `grep -r "InboxSentinel\|Roda\|Rodalega\|Supabase" . --include="*.md" --include="*.yaml"`.

---

## L-003 — Visibility policy must include all doc folders

**Mistake:** `docs/README.md` listed visibility rules for `docs/architecture/`, `docs/adr/`, `docs/api/` but did not mention `docs/brand/` or `docs/research/` when those folders were created.  
**Rule:** Whenever a new folder is added under `docs/`, update `docs/README.md` immediately to declare it public or private.

---

## L-004 — Supabase was superseded; never re-introduce it

**Mistake:** ADR-0004 originally chose Supabase. After switching to Neon + Better Auth, several files still referenced Supabase URIs, environment variables, and SDK calls.  
**Rule:** Neon PostgreSQL (prod) + SQLite (dev) is the canonical DB choice per ADR-0004. Never suggest or generate Supabase SDK code, Supabase `DATABASE_URL` formats, or `supabase-py`.

---

## L-005 — Private ADRs must never be committed

**Mistake:** ADRs 0001, 0006, 0007 were previously committed to git history before the gitignore policy was in place.  
**Rule:** Before committing, run `git status` and confirm none of the gitignored private files appear as staged. The private files are: `docs/ops/`, `docs/architecture/threat-model.md`, `docs/architecture/privacy-rgpd.md`, `docs/adr/0001-*`, `docs/adr/0006-*`, `docs/adr/0007-*`.

---

## L-006 — Execution plans belong in tasks/, not docs/research/

**Mistake:** `bloc-by-bloc-tasks-v2.md` (the full Simplon task plan) was placed in `docs/research/`. Research is reference material; execution plans are work artifacts.  
**Rule:** Active task plans live in `tasks/TASK_PLAN.md`. Reference material (competitive analysis, data sources, tech surveys) lives in `docs/research/`.

---

## L-007 — Gmail watch renewal must use Cloud Scheduler, not in-process background task

**Decision:** `users.watch` expires after 7 days. Renewal runs every 6 days via Cloud Scheduler → `POST /internal/renew-watches` on `sicurre-api`.  
**Rule:** Never implement watch renewal as an APScheduler or threading background task inside the API. Cloud Run scales to zero — in-process schedulers die silently. Multiple instances also cause duplicate `users.watch` calls (race condition).  
**IAM:** The `/internal/renew-watches` endpoint is restricted to the Cloud Scheduler service account via `roles/run.invoker`. No shared API key.
