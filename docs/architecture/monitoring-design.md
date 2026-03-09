# Monitoring Design

## Purpose

This document makes monitoring a public and certification-visible part of the architecture.

It complements the private operational notes in `docs/ops/` and defines the scope of the final delivery bloc dedicated to observability and operational readiness.

## Why monitoring is a delivery bloc

Monitoring is not a side note.
It supports multiple certification expectations:

- model-side monitoring and quality feedback
- application monitoring and alerting
- incident detection and resolution traceability
- operational readiness for demonstration and defense

## Scope

Monitoring in Sicurre covers five layers:

1. API health and availability
2. ingestion and remediation workflow health
3. model inference quality and latency
4. application runtime logs and alerts
5. incident investigation and documented resolution

## Public monitoring targets

### Health checks

- API health endpoint
- classifier service availability
- listener availability where applicable

### Logs

- structured JSON logs
- correlation identifiers for ingestion, message flow, and remediation events
- redaction of personal and sensitive data before emission

### Metrics

- request volume
- latency
- error rate
- verdict distribution
- remediation success rate
- watch renewal and listener health

### Alerts

- ingestion failures
- classifier failure spikes
- missing notifications for a configured time window
- latency degradation beyond target thresholds

### Incident handling

- identify root cause
- reproduce the issue in development or test
- document the fix path
- link the incident to issue tracking and evidence

## Delivery outputs

Expected outputs for the monitoring bloc include:

- public monitoring design
- private operational runbooks and alert details
- instrumented services and dashboards
- documented incident example
- traceable link between monitoring findings and corrective work

## Relation to the rest of the architecture

Monitoring is cross-cutting.
It does not replace the data, model, or app domains.
It observes them and provides the evidence needed to prove operational control.