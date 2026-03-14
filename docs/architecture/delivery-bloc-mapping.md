# Delivery Bloc Mapping

## Purpose

This document clarifies the difference between the official certification structure and the internal execution structure used for Sicurre.

The Simplon referential defines 3 official competency blocs.
Sicurre is executed through Bloc 0 plus 5 delivery blocs so that planning, backlog management, and evidence production stay explicit and manageable.

## Official certification blocs

| Official bloc | Competency scope | Main competencies |
|---------------|------------------|-------------------|
| Bloc 1 | Data collection, storage, and access | C1 to C5 |
| Bloc 2 | AI service selection, integration, model API, and MLOps | C6 to C13 |
| Bloc 3 | Application design, implementation, CI/CD, and operations | C14 to C21 |

## Internal delivery structure

| Delivery bloc | Purpose | Primary evidence |
|---------------|---------|------------------|
| Bloc 0 | Project reset, architecture freeze, backlog and governance baseline | architecture docs, task plan, GitHub board, milestones |
| Bloc 1 | Data platform | source connectors, SQL schema, data API, curated datasets |
| Bloc 2 | Technical survey and stack decision | benchmark, rejected options, feasibility notes, implementation decision |
| Bloc 3 | Model | classifier API, evaluation flow, model contracts, test evidence |
| Bloc 4 | App | pre-app validation evidence, application integration, auth, remediation flows, UI-connected endpoints |
| Bloc 5 | Monitoring | logs, metrics, alerts, incident handling, monitoring documentation |

## Mapping between certification and delivery blocs

The mapping is not one-to-one.

| Delivery bloc | Main certification coverage | Notes |
|---------------|-----------------------------|-------|
| Bloc 0 | supports all blocs | establishes the execution baseline and evidence trail |
| Bloc 1 | Bloc 1, C1 to C5 | direct coverage of collection, storage, RGPD, and Data API |
| Bloc 2 | Bloc 2, C6 to C8 | benchmark, technical survey, service choice, and implementation decision |
| Bloc 3 | Bloc 2, C9 to C13 | model-serving API, tests, CI/CD, and model-side monitoring |
| Bloc 4 | Bloc 3, C14 to C19 | application design, development, integration, CI/CD |
| Bloc 5 | Bloc 2 and Bloc 3, especially C11, C20, C21 | monitoring spans both the model and the application runtime |

## Planning rule

All public architecture and planning documents should:

- preserve the official 3-bloc certification language when referring to competencies
- use Bloc 0 plus 5 delivery blocs when organizing milestones, backlog, and implementation order

This prevents a recurring ambiguity where the architecture looks correct but the execution plan hides important work such as technical survey or monitoring.

## Current repository interpretation

- the data platform is already well documented
- the technical survey exists in research notes and should stay as an early decision bloc
- proof-of-concept validation evidence should be recorded at the start of Bloc 4, after a usable model baseline exists and before full app integration
- model and app work already exist conceptually in the architecture
- monitoring exists in private ops notes and must now also exist in public, certification-visible architecture documents