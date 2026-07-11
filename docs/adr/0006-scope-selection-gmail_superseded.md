# ADR-0006: Gmail scope selection and verification readiness

**Date:** 2026-02-28  
**Status:** Superseded by [ADR-0006: Cloudflare token scope selection](0006-cloudflare-token-scope-selection.md)  

## Context
Sicurre needs to move phishing emails to Trash, which requires write capabilities.

## Decision
Request the narrowest Gmail scopes that enable remediation, and document verification readiness for sensitive/restricted scopes.

## Notes
Gmail API scopes are categorized; sensitive/restricted scopes may require verification steps and policy compliance. Use minimal scopes and be ready with privacy policy and data handling documentation.
