"""Idempotently grant or revoke Sicurre platform-admin access in an env file."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ADMIN_KEY = "SICURRE_PLATFORM_ADMIN_EMAILS"
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _parse_admins(contents: str) -> set[str]:
    for line in contents.splitlines():
        if line.startswith(f"{ADMIN_KEY}="):
            return {
                email.strip().lower()
                for email in line.partition("=")[2].split(",")
                if email.strip()
            }
    return set()


def update_admin_allowlist(contents: str, *, email: str, action: str) -> tuple[str, bool]:
    """Return updated env contents and whether the allowlist changed."""
    normalized_email = email.strip().lower()
    if EMAIL_PATTERN.fullmatch(normalized_email) is None:
        raise ValueError("A valid admin email is required")
    if action not in {"grant", "revoke"}:
        raise ValueError("Action must be grant or revoke")

    admins = _parse_admins(contents)
    before = admins.copy()
    if action == "grant":
        admins.add(normalized_email)
    else:
        admins.discard(normalized_email)
    if admins == before:
        return contents, False

    replacement = f"{ADMIN_KEY}={','.join(sorted(admins))}"
    lines = contents.splitlines()
    existing_index = next(
        (index for index, line in enumerate(lines) if line.startswith(f"{ADMIN_KEY}=")),
        None,
    )
    if existing_index is None:
        lines.append(replacement)
    else:
        lines[existing_index] = replacement
    suffix = "\n" if contents.endswith("\n") or not contents else ""
    return "\n".join(lines) + suffix, True


def main() -> int:
    """Update the requested environment file without creating user credentials."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("grant", "revoke"))
    parser.add_argument("--email", required=True)
    parser.add_argument("--env-file", type=Path, default=Path("deploy/env.api"))
    args = parser.parse_args()

    if not args.env_file.is_file():
        parser.error(f"Environment file does not exist: {args.env_file}")
    current = args.env_file.read_text(encoding="utf-8")
    updated, changed = update_admin_allowlist(
        current,
        email=args.email,
        action=args.action,
    )
    if changed:
        args.env_file.write_text(updated, encoding="utf-8")
    print(
        f"{args.email.lower()} {'updated' if changed else 'already correct'}; "
        "restart sicurre-api to apply the allowlist."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
