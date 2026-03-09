# Architecture Overview (Sicurre)

The architecture is now documented in a certification-first order.

## Reading order

1. Bloc 1 backbone: [data-design.md](data-design.md)
2. Component architecture across the 3 blocs: [component-design.md](component-design.md)
3. Backend target organization: [backend-plan.md](backend-plan.md)
4. Product runtime context: [system-context.md](system-context.md)

## Architectural stance

Sicurre should be understood as a progression:

- experimental corpus and notebooks
- structured data platform
- AI service layer
- SaaS application runtime

The certification requires the data platform to be explicit and defensible on its own.
The product branch springs from that foundation rather than replacing it.

## Key design choices

- Bloc 1 is centered on a SQL-backed data platform and REST data API
- Bloc 2 consumes curated datasets from the data platform and exposes the classifier as an API
- Bloc 3 integrates the classifier into the end-user application
- FastAPI remains the API framework target
- PostgreSQL remains the production database target, with SQLite compatibility for development and CI
