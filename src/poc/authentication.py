"""Local authentication persistence for the certification POC."""

from __future__ import annotations

import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import bcrypt

from poc.presentation.formatting import hash_token


class PocAuthStore:
    """Provide explicit, short-lived access to the isolated POC auth database."""

    def __init__(self, database_path: Path) -> None:
        """Configure the store without opening a database connection."""
        self._database_path = database_path

    def query(self, query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        """Execute a read query and return rows with named access."""
        connection = sqlite3.connect(str(self._database_path))
        connection.row_factory = sqlite3.Row
        try:
            return connection.execute(query, params).fetchall()
        finally:
            connection.close()

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> None:
        """Execute and commit a write query."""
        connection = sqlite3.connect(str(self._database_path))
        try:
            connection.execute(query, params)
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def password_matches(plain_password: str, hashed_password: str) -> bool:
        """Verify a bcrypt password hash, returning false for malformed hashes."""
        try:
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
        except (TypeError, ValueError):
            return False

    def authenticate(self, email: str, password: str) -> dict[str, Any] | None:
        """Authenticate a normalized email without revealing account existence."""
        rows = self.query("SELECT * FROM poc_user WHERE email = ?", (email.strip().lower(),))
        if not rows:
            return None
        user = dict(rows[0])
        return user if self.password_matches(password, user["password_hash"]) else None

    def create_session(self, user_id: str, now: datetime | None = None) -> str:
        """Create a seven-day remembered session and persist only its hash."""
        session_id = secrets.token_urlsafe(32)
        current_time = now or datetime.now(UTC)
        expires_at = (current_time + timedelta(days=7)).isoformat()
        self.execute(
            "UPDATE poc_user SET session_token_hash = ?, session_expires_at = ? WHERE id = ?",
            (hash_token(session_id), expires_at, user_id),
        )
        return session_id

    def resolve_session(
        self, session_id: str, now: datetime | None = None
    ) -> dict[str, Any] | None:
        """Resolve a non-expired remembered session to its local user."""
        current_time = now or datetime.now(UTC)
        rows = self.query(
            """
            SELECT *
            FROM poc_user
            WHERE session_token_hash = ?
              AND session_expires_at IS NOT NULL
              AND session_expires_at > ?
            LIMIT 1
            """,
            (hash_token(session_id), current_time.isoformat()),
        )
        return dict(rows[0]) if rows else None

    def revoke_session(self, user_id: str) -> None:
        """Remove the remembered session for a user."""
        self.execute(
            "UPDATE poc_user SET session_token_hash = NULL, session_expires_at = NULL WHERE id = ?",
            (user_id,),
        )

    def record_login(self, user_id: str, now: datetime | None = None) -> None:
        """Record the latest successful local login time."""
        self.execute(
            "UPDATE poc_user SET last_login_at = ? WHERE id = ?",
            ((now or datetime.now(UTC)).isoformat(), user_id),
        )
