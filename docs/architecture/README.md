# Architecture Overview (Sicurre)

Sicurre is a **French-first phishing protection** product for auto-entrepreneurs and TPEs. It operates as a **post-delivery** remediation system on Gmail and (later) Microsoft 365: emails arrive, Sicurre is notified, Sicurre classifies, and malicious emails are automatically moved to Trash/quarantine.

## Primary workflow
1. User connects Gmail via OAuth
2. Sicurre configures Gmail push notifications (`users.watch`) to a Pub/Sub topic
3. Pub/Sub push delivers mailbox change events to a Cloud Run endpoint
4. Sicurre fetches the changed message(s), classifies, and if phishing: trashes it
5. Sicurre stores an audit log + offers undo/restore

## Key design choices (see ADRs)
- Post-delivery architecture (not MX pre-delivery)
- French-native transformer base (CamemBERTav2, DeBERTaV3 architecture, 3-class: phishing/spam/legitimate)
- Open-core: open-source model weights, paid managed product
- Cloud Run + FastAPI for minimal ops and autoscaling
