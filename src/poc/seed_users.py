"""Seed the local auth users for the Streamlit POC."""

from __future__ import annotations

from poc.local_runtime import POC_AUTH_DB_PATH, demo_accounts, ensure_local_auth_db


def main() -> None:
    ensure_local_auth_db()
    print(f"POC auth database ready: {POC_AUTH_DB_PATH}")
    for account in demo_accounts():
        print(f"  {account['role']}: {account['email']}")


if __name__ == "__main__":
    main()
