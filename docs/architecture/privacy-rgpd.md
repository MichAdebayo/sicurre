# Privacy & RGPD

## Principles
- Data minimization
- Purpose limitation (phishing protection only)
- Storage limitation (retention + deletion)
- Security by design

## Default storage
- Store: message_id, timestamps, verdict, confidence, signals, action taken
- Do NOT store: full raw email body (unless user explicitly opts-in)

## User rights
- Export personal data: provide download endpoint
- Deletion: delete user + tokens + logs upon request

## Security controls
- Encrypt integration tokens and shared secrets
- Access control (RBAC for admin)
- Audit trail for sensitive actions

## Notes
The implemented runtime uses Cloudflare Email Routing and a Cloudflare Email Worker rather than restricted mailbox OAuth scopes.
- GDPR / data minimisation: User PII (sessions, Cloudflare integration metadata, threat logs, quarantine records, feedback) sits in sicurre_app. Raw scraped email URLs and ML training data sit in sicurre_data_platform. These have different retention rules, different breach notification obligations, and different access policies. Keeping them together creates a compliance risk.
