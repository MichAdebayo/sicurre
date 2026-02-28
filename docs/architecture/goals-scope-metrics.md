# Product goals, scope, and success metrics

## Product goals
- Reduce phishing victimization for French SMBs via automatic remediation
- Build trust through explainability (“why flagged”) + undo capability
- Maintain low operational cost (bootstrappable)

## In-scope (MVP)
- Gmail integration (OAuth + watch)
- Phishing classification API (French-first)
- Automatic remediation: move phishing emails to Trash
- Audit log + dashboard
- Feedback loop: “correct/incorrect” user labels for retraining

## Out-of-scope (MVP)
- True pre-delivery interception via MX/SMTP relay
- Enterprise SOC/MDR functionality
- Large-scale DLP / compliance archiving
- Attachment sandbox detonation (possible later)

## Success metrics (MVP)
- Time-to-remediate (TTR): p95 < 5 seconds from delivery to Trash
- Model performance: F1 ≥ 0.95 on French phishing evaluation set (internal)
- False positives: ≤ 0.5% on validated “legit” emails
- Availability: 99.5% monthly for API + ingestion
- Cost: infra cost per active inbox ≤ €0.20/month under free tiers where possible
