# Threat model

## Assets

| Asset | Sensitivity | Location |
|-------|------------|----------|
| Cloudflare API tokens / Worker shared secrets | **Critical** | Integration token storage, encrypted at rest |
| User PII (email, display_name) | **High** | `users` table |
| Threat log / audit data | **Moderate** | `threat_log` table |
| Classifier model weights | **Low** | Public on HuggingFace (open-core) |
| Infrastructure credentials (DB URL, Better Auth secret, encryption key) | **Critical** | Deployment environment or host secret store |
| Session tokens | **High** | `sessions` table + client cookies |

## STRIDE Threat Analysis

### 1. Spoofing — Forged Worker Scan Request
- **Attack:** Attacker sends fake scan requests to `POST /v1/email/scan` to poison logs, trigger false quarantine records, or consume inference capacity.
- **Mitigation:**
  - Require `X-Sicurre-Secret` shared secret for Worker-originated scan requests.
  - Rate-limit the scan endpoint and reject oversized payloads before inference.
  - Bind scan events to a configured workspace/domain where possible.

### 2. Tampering — Integration Token Theft / Manipulation
- **Attack:** Attacker gains access to DB and extracts encrypted Cloudflare tokens; or compromises the encryption key.
- **Mitigation:**
  - Encrypt integration tokens with AES-256-GCM; encryption key is separate from DB credentials.
  - Rotate encryption key quarterly; re-encrypt tokens on rotation.
  - Minimal Cloudflare token permissions, scoped to the protected zone.
  - DB connection uses TLS (Neon enforces this by default).

### 3. Repudiation — Untracked Actions
- **Attack:** Legitimate user disputes that an email was quarantined/released, or attacker covers tracks.
- **Mitigation:**
  - Every classification + action is logged to `threat_log` with timestamps, model version, and verdict.
  - Logs are append-only (API never deletes threat_log rows; retention policy handles cleanup).
  - User can view full audit trail in dashboard.

### 4. Information Disclosure — Data Leakage (RGPD)
- **Attack:** Email bodies, PII, or classification metadata exposed through logs, error messages, or API responses.
- **Mitigation:**
  - **Do not store raw email bodies** (default). If user opts in, store anonymized text with 7–90 day TTL.
  - Anonymize PII in any stored text: `[EMAIL]`, `[PHONE]`, `[IBAN]`, `[URL]`.
  - API error responses never include internal state, stack traces, or DB details.
  - Structured logging (JSON) with PII redaction filter.
  - Retention limits enforced by scheduled cleanup job (12 months for audit metadata).

### 5. Denial of Service — Worker/API Flood
- **Attack:** Overwhelming `/v1/email/scan`; or flooding `/v1/model/classify` with expensive inference requests.
- **Mitigation:**
  - Rate limiting on public endpoints (per-user token bucket via `slowapi`) — see ADR-0009 for per-endpoint limits.
  - Worker endpoint: validate shared secret before any processing (reject fast).
  - `/v1/model/classify`: require API key + plan-aware rate limit per key.

### 6. Elevation of Privilege — Cross-User Data Access
- **Attack:** User A accesses User B's threat logs, tokens, or emails through API parameter manipulation (IDOR).
- **Mitigation:**
  - All API queries filter by `user_id` from the authenticated session (never from request body).
- Cloudflare integration, threat, quarantine, and feedback queries always filter by workspace/user from the authenticated session.
  - Integration tests for IDOR on every endpoint.

## Additional Threats

### Prompt Injection / Model Manipulation
- **Attack:** Phishing email contains adversarial text designed to evade the classifier (e.g., invisible Unicode, prompt-like instructions).
- **Mitigation:**
  - Classifier treats email as **data only** — no instruction-following.
  - Input normalization: strip zero-width characters, normalize Unicode, limit input length.
  - Hybrid signals (DMARC, URL heuristics) provide fallback when NLP confidence is low.

### False Positives Leading to Lost Mail
- **Attack:** Legitimate email classified as phishing and quarantined → user misses important message.
- **Mitigation:**
  - Quarantine keeps a recoverable item with explicit release and allow-list actions.
  - Dashboard provides release/restore actions via `/v1/quarantine/*` and `/v1/threats/{id}/status`.
  - Confidence threshold tuning: only quarantine above configurable threshold (default 0.85).
  - Feedback loop: user-reported false positives feed into retraining pipeline.

### Supply Chain — Compromised Model Weights
- **Attack:** Attacker uploads tampered model weights to HuggingFace.
- **Mitigation:**
  - Pin model versions with SHA-256 checksums in `model_versions` table.
  - Model promotion requires explicit API call (not automatic pull from HuggingFace).
  - Sign model artifacts (future: Sigstore for ML artifacts).
