# Product goals, scope, and success metrics

## Product goals
- Reduce phishing victimization for French SMBs through pre-delivery domain email scanning and controlled quarantine
- Build trust through explainability (“why flagged”) + undo capability
- Maintain low operational cost (bootstrappable)

## In-scope (MVP)
- Cloudflare Email Routing integration for customer-owned domains
- Cloudflare Email Worker calling Sicurre API `POST /v1/email/scan`
- Phishing classification API (French-first)
- Quarantine workflow: hold, deliver, delete, and allow-list sender
- Audit log + dashboard
- Feedback loop: false positive / false negative reports stored in `app_feedback`

## Out-of-scope (MVP)
- Gmail watch / Pub/Sub runtime ingestion
- Enterprise SOC/MDR functionality
- Large-scale DLP / compliance archiving
- Attachment sandbox detonation (possible later)

## Success metrics (MVP)
- Time-to-classify: p95 within configured SLA from Worker callback to verdict
- Model performance: F1 ≥ 0.95 on French phishing evaluation set (internal)
- False positives: ≤ 0.5% on validated “legit” emails
- Availability: 99.5% monthly for API + ingestion
- Cost: infra cost per active inbox ≤ €0.20/month under free tiers where possible
