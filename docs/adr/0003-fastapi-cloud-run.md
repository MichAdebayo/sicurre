# ADR-0003: FastAPI + Cloud Run for serving

**Date:** 2026-02-28  
**Status:** Accepted  

## Context
Bootstrapped build: minimize ops overhead, support autoscaling, keep costs low.

## Decision
Use FastAPI for APIs and deploy on Google Cloud Run.

## Alternatives
- Flask: less async-native
- Kubernetes: too heavy for MVP
- VM hosting: more maintenance

## Consequences
- Simple deployments, autoscaling
- Cold start considerations; mitigate with min instances if needed later
