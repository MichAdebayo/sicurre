# ADR-0003: FastAPI + Cloud Run for serving

**Date:** 2026-02-28  
**Status:** Accepted  

## Context
Bootstrapped build: minimize ops overhead, support autoscaling, keep costs low. The API layer must serve ML inference (CamemBERTav2), handle Gmail Pub/Sub webhooks, and proxy auth flows — all with high concurrency and low latency on Cloud Run's container-based serverless platform.

## Decision
Use FastAPI for all API services and deploy on Google Cloud Run.

## Alternatives considered

| Option | Pros | Cons |
|--------|------|------|
| **Django + DRF** | Batteries-included (ORM, admin, auth, migrations); large ecosystem; well-known in French dev community | Sync-first WSGI model is a poor fit for async Pub/Sub handlers and ML serving; Django admin is unnecessary (we have no admin panel requirement); heavier cold-start on Cloud Run; ORM overhead when we only need thin SQL via SQLAlchemy/SQLModel |
| **Flask** | Lightweight, familiar | Less async-native than FastAPI; no built-in validation/OpenAPI generation; would need many extensions (marshmallow, flask-cors, etc.) |
| **Kubernetes (GKE)** | Full orchestration, auto-healing | Massive ops overhead for a solo dev at MVP; cost floor too high |
| **VM hosting (GCE/EC2)** | Full control | Manual scaling, patching, monitoring — not viable for solo dev |

### Why not Django specifically
1. **Async-native requirement:** Gmail Pub/Sub push handlers and ML inference benefit from `async def` endpoints. Django's async support (ASGI) is still maturing — many ORM operations remain sync-only, requiring `sync_to_async` wrappers.
2. **ML serving boundary:** FastAPI + Pydantic gives automatic request/response validation and OpenAPI spec generation — critical for the classifier API contract. Django REST Framework can do this, but with more boilerplate.
3. **Cloud Run alignment:** FastAPI's Uvicorn ASGI server has faster cold-start and lower memory footprint than Django + Gunicorn on Cloud Run's container model.
4. **No admin panel needed:** Django's strongest feature (admin interface) is unused — Sicurre has no back-office requirement for MVP.
5. **Simplon alignment:** Demonstrates competency in modern Python async frameworks (Bloc 3 C18: "Développer une API").

## Consequences
- Simple deployments, autoscaling, pay-per-request billing
- Cold start considerations; mitigate with `min-instances=1` if needed later
- Must manually set up migrations (Alembic) and admin tooling if ever needed — acceptable trade-off for MVP speed
