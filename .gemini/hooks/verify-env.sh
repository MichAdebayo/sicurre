#!/bin/bash
# Gemini CLI hook: verify-env
# Ensures local secret credentials are not staged in git.

# Log status to stderr
echo "[Hook: verify-env] Checking environment variables staging status..." >&2

# Check if any .env files are currently staged
if git diff --cached --name-only | grep -E -q "\.env|\.env\..*"; then
    echo "🚨 SECURITY ALERT: Staging .env files is blocked to prevent exposing API keys." >&2
    exit 2
fi

# Print final empty JSON object on stdout for successful completion
echo "{}"
exit 0
