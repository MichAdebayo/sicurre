# Data design

## Data classes
- User identity + OAuth linkage (minimal)
- Email metadata for audit (minimal)
- Optional: anonymized email text for model improvements (time-limited)

## Suggested tables (high-level)
- `users`: id, email, created_at
- `oauth_tokens`: user_id, provider, encrypted_refresh_token, scopes, updated_at
- `threat_log`: id, user_id, message_id, received_at, verdict, confidence, signals_json, model_version, action_taken, action_at
- `feedback`: threat_log_id, user_id, feedback_label, feedback_at

## Retention policy (default)
- Audit metadata: 12 months
- Raw email bodies: 0 days (do not store) OR 7–90 days if user opts in
- Anonymized training text: 90 days rolling, then delete

## Anonymization rules (if storing text)
- Replace emails with `[EMAIL]`
- Replace phone numbers with `[PHONE]`
- Replace IBAN with `[IBAN]`
- Replace URLs with `[URL]` (store domain separately if needed)
