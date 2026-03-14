# Architecture Overview (Sicurre)

The architecture is now documented in a certification-first order.

Two planning lenses coexist and must not be confused:

- official certification blocs: 3 blocs defined by the Simplon referential
- internal delivery blocs: Bloc 0 plus 5 execution blocs used to organize implementation and evidence

## Reading order

1. Delivery model and bloc mapping: [delivery-bloc-mapping.md](delivery-bloc-mapping.md)
2. Bloc 1 backbone: [data-design.md](data-design.md)
3. Bloc 1 source perimeter: [source-perimeter.md](source-perimeter.md)
4. Cross-bloc component architecture: [component-design.md](component-design.md)
5. Backend target organization: [backend-plan.md](backend-plan.md)
6. Public monitoring architecture: [monitoring-design.md](monitoring-design.md)
7. Product runtime context: [system-context.md](system-context.md)

## Architectural stance

Sicurre should be understood as a progression:

- exploratory corpus, notebooks, and architecture review
- structured data platform
- technical survey and proof of concept
- model and service layer
- SaaS application runtime
- monitoring and operational hardening

The certification requires the data platform to be explicit and defensible on its own.
The product branch springs from that foundation rather than replacing it.

## Key design choices

- Bloc 1 is centered on a SQL-backed data platform and REST data API
- the technical survey and POC phase validates stack choices before full implementation resumes
- the model layer consumes curated datasets from the data platform and exposes the classifier as an API
- the application layer integrates the classifier into the end-user application
- monitoring is treated as a first-class delivery bloc rather than an afterthought hidden in private ops notes
- FastAPI remains the API framework target
- PostgreSQL remains the production database target, with SQLite compatibility for development and CI
