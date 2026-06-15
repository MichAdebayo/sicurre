#!/bin/bash
# Gemini CLI hook: block-destructive-commands
# Scans tool execution command arguments to prevent destructive operations.

# Read JSON payload from stdin
stdin_payload=$(cat)

echo "[Hook: block-destructive-commands] Scanning command line for safety..." >&2

# Detect destructive commands in stdin payload
if echo "$stdin_payload" | grep -E -i -q "rm -rf /|mkfs|dd if|sudo rm|format|drop database|wipe db"; then
    echo "🚨 SECURITY BLOCKED: Destructive or unauthorized system command execution prevented by security hook." >&2
    exit 2
fi

# Print final empty JSON object on stdout for successful completion
echo "{}"
exit 0
