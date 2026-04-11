# AGENTS.md — Sicurre

## Repo Overview

Sicurre is a French-native, real-time phishing detection and inbox remediation system. It classifies emails into three classes (phishing, spam, legitimate) with a fine-tuned CamemBERTav2 (DeBERTaV3-based) model and automatically moves phishing to Gmail Trash within 2 seconds. Target market: French auto-entrepreneurs and TPEs.

**Branch:** `docs/architecture` (current). Application code lives in future branches.  
**Full instructions for GitHub Copilot:** `.github/copilot-instructions.md`

---

## Setup

```bash
# Install dependencies
uv sync

# Run tests (when src/ exists)
uv run pytest

# Run API locally (when src/ exists)
uv run uvicorn src.data_platform.api.main:app --reload
```

---

## Architecture (read before editing)

| Component | Role | Language | Docs |
|-----------|------|----------|------|
| `sicurre-api` | FastAPI — auth, audit log, public API | Python 3.11 | ADR-0003, ADR-0008 |
| `gmail-listener` | Cloud Run — Pub/Sub push handler | Python 3.11 | ADR-0001, ADR-0007 |
| `phishing-api` | Cloud Run — CamemBERTav2 ONNX inference (3-class: phishing/spam/legit) | Python 3.11 | ADR-0002 |
| Dashboard (POC) | Streamlit — Simplon evaluation only | Python | — |
| Dashboard (prod) | React/TypeScript | TypeScript | — |
| DB | Neon PostgreSQL (prod) / SQLite (dev) | SQL | ADR-0004 |
| Auth | Better Auth (Node.js sidecar) | TypeScript | ADR-0008 |

**Canonical DB schema:** `docs/architecture/data-design.md`  
**Canonical API spec:** `docs/api/openapi.yaml`  
**Brand identity (colors, fonts, motion, French copy):** `docs/brand/brand-identity.md`  
**Frontend skill:** `.vscode/skills/frontend-agent/SKILL.md`  
**All ADRs:** `docs/adr/`

---

## Workflow Orchestration

### 1. Plan Mode Default
- Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions).
- If something goes sideways, STOP and re-plan immediately — don't keep pushing.
- Use plan mode for verification steps, not just building.
- Write detailed specs upfront to reduce ambiguity.

### 2. Subagent Strategy
- Use subagents liberally to keep the main context window clean.
- Offload research, exploration, and parallel analysis to subagents.
- For complex problems, throw more compute at it via subagents.
- One task per subagent for focused execution.

### 3. Self-Improvement Loop
- After ANY correction from the user: update `tasks/lessons.md` with the pattern.
- Write rules for yourself that prevent the same mistake.
- Ruthlessly iterate on these lessons until mistake rate drops.
- Review `tasks/lessons.md` at the start of each session for this project.

### 4. Verification Before Done
- Never mark a task complete without proving it works.
- Diff behaviour between main and your changes when relevant.
- Ask yourself: "Would a staff engineer approve this?"
- Run tests, check logs, demonstrate correctness.

### 5. Demand Elegance (Balanced)
- For non-trivial changes: pause and ask "is there a more elegant way?"
- If a fix feels hacky: "Knowing everything I know now, implement the elegant solution."
- Skip this for simple, obvious fixes — don't over-engineer.
- Challenge your own work before presenting it.

### 6. Autonomous Bug Fixing
- When given a bug report: just fix it. Don't ask for hand-holding.
- Point at logs, errors, and failing tests — then resolve them.
- Zero context switching required from the user.
- Go fix failing CI tests without being told how.

---

## Task Management

1. **Plan First:** Write plan to `tasks/todo.md` with checkable items.
2. **Verify Plan:** Check in before starting implementation.
3. **Track Progress:** Mark items complete as you go.
4. **Explain Changes:** High-level summary at each step.
5. **Document Results:** Add a review section to `tasks/todo.md`.
6. **Capture Lessons:** Update `tasks/lessons.md` after any correction.

---

## Core Principles

- **Simplicity First:** Make every change as simple as possible. Minimal code impact.
- **No Laziness:** Find root causes. No temporary fixes. Senior developer standards.
- **Minimal Impact:** Changes should only touch what is necessary. Avoid introducing bugs.

---

## Code Quality — OOP & Clean Code

Apply these principles to **all** production code. No exceptions.

### SOLID Principles
- **Single Responsibility (SRP):** One class/module = one reason to change. A scraper class does not also clean data. A classifier does not also write to the database.
- **Open/Closed (OCP):** Extend via new classes or strategy patterns, not by modifying existing working code. Example: new data sources implement a `BaseExtractor` interface — don't add `if source == "new_thing"` branches.
- **Liskov Substitution (LSP):** Subclasses must be drop-in replacements for their parent. If `CERTFRExtractor` extends `BaseExtractor`, it must honour the same contract.
- **Interface Segregation (ISP):** Keep interfaces small and focused. Don't force a class to implement methods it doesn't need.
- **Dependency Inversion (DIP):** Depend on abstractions (protocols/ABCs), not concrete implementations. Inject dependencies — don't instantiate them inside business logic.

### Clean Code Rules
- **Modular structure:** Each script/module does ONE thing. Make-facing operational entrypoints live under `src/data_platform/cli/`, scheduled runners live under `src/data_platform/cron_schedulers/`, and reusable business logic lives under `src/data_platform/`. `scripts/` is reserved for quick investigation, recovery utilities, and no-write probes only. Source-facing fetch/parse/persist logic belongs in `src/data_platform/extractors/` or `src/data_platform/services/`. No god-files.
- **Meaningful names:** `extract_french_phishing_urls()` — not `do_stuff()` or `process()`. Variable names describe content: `raw_emails`, `cleaned_df`, `phishing_samples`.
- **Small functions:** Max ~20 lines per function. If a function needs a comment to explain *what* it does, it's too long — extract a well-named helper.
- **No magic numbers/strings:** Use constants or enums. `CONFIDENCE_THRESHOLD = 0.85` — not `if score > 0.85`.
- **DRY (Don't Repeat Yourself):** Shared logic lives in `src/common/` or `src/utils/`. Two scripts doing the same CSV normalization = refactor into one reusable function.
- **Type hints everywhere:** Every function signature, every return type. Use `Protocol` for duck-typing interfaces.
- **Docstrings on public APIs:** Google-style docstrings on all public classes and functions. Internal helpers get a one-liner if non-obvious.
- **Error handling:** Catch specific exceptions, never bare `except:`. Log context. Re-raise or return typed errors — don't swallow silently.
- **No side effects in constructors:** `__init__` sets state. It does not make HTTP calls, read files, or connect to databases. Use factory methods or explicit `.connect()` / `.load()` calls.

### Project Structure Convention
```
src/
├── core/            # Core configuration, security, DB connections
├── db/              # Consolidated database layer
│   ├── models/      # SQLModel/SQLAlchemy entities
│   ├── queries/     # Repository/Query logic
│   ├── services/    # DB-heavy business services
│   └── migrations/  # Alembic environment
├── data_platform/   # Specific data domain
│   ├── api/         # Data ingestion/curation API
│   ├── extractors/  # Source-specific connectors
│   ├── cleaning/    # Normalization logic
│   ├── services/    # Domain services (adaptation, snapshot)
│   └── cron_schedulers/
└── app/             # (Future) User-facing application domain

scripts/             # Operational scripts (monorepo root)
├── data_platform/
└── app/

notebooks/           # Exploratory work (monorepo root)
├── data_platform/
└── app/

data/
└── local/           # Local SQLite (sicurre.db) and SQL exports
```

---

## Hard Rules

### Database
- `sicurre-api` is the **only** service that connects to the database. `gmail-listener` and `phishing-api` call `sicurre-api` over HTTP — they have no DB credentials.
- Every query on user-scoped tables (`threat_log`, `oauth_tokens`, `feedback`, `sessions`) **must** filter by `user_id` from the authenticated session. Never from request parameters.

### Security
- Never log or return refresh tokens. They live encrypted (AES-256-GCM) in `oauth_tokens.encrypted_refresh_token` only.
- Every new public endpoint needs a `slowapi` rate limit. See `docs/adr/0009-caching-and-rate-limiting.md` for the rate limit table.
- Error responses: no stack traces, no DB details, no internal state.

### Privacy
- Do not store raw email bodies by default. Any email content storage must be opt-in, anonymized, and TTL-bounded.
- Anonymize PII before storing: `[EMAIL]`, `[PHONE]`, `[IBAN]`, `[URL]`.

### Idempotency
- All Pub/Sub push handlers must be idempotent. The `UNIQUE (user_id, message_id)` constraint on `threat_log` is the deduplication guard.

---

## Code Style

- Python 3.11+, fully type-annotated.
- `async def` for all FastAPI handlers and I/O-bound functions.
- Use `httpx.AsyncClient` for outbound HTTP (not `requests`).
- Pydantic v2 models for all request/response schemas.
- Config via `pydantic-settings` `BaseSettings`. No `os.environ` in business logic.
- Secrets in `.env` (dev) or GCP Secret Manager (prod). Never hardcoded.

---

## Tests

```bash
uv run pytest                        # all tests
uv run pytest -k "test_idor"         # IDOR tests only
uv run pytest -k "test_idempotent"   # idempotency tests
uv run pytest --cov=src              # with coverage
```

- Every user-scoped endpoint needs an IDOR test: auth as User A, request User B's resource, assert `403` or `404`.
- DB tests use SQLite in-memory (`sqlite:///:memory:`). No Neon connection in CI.
- Mock Gmail API with `respx` or `pytest-httpx`.
- Mock Pub/Sub push with a plain HTTP POST to the listener endpoint.

---

## Warnings

- **Do not recreate or commit** these gitignored private files: `docs/ops/`, `docs/architecture/threat-model.md`, `docs/architecture/privacy-rgpd.md`, `docs/adr/0001-post-delivery-gmail.md`, `docs/adr/0006-scope-selection-gmail.md`, `docs/adr/0007-idempotency-pubsub-history.md`. They exist locally but must never appear in git history.
- **Do not add Supabase** as a dependency. Database is Neon PostgreSQL / SQLite (see ADR-0004).
- **Do not use Django or Flask.** FastAPI only (ADR-0003).
- **Do not connect non-API services to the DB.** Route everything through `sicurre-api`.
- **Do not store Gmail `message_id` as a unique key across users.** The uniqueness constraint is `(user_id, message_id)`.
