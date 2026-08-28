"""Framework-independent session state orchestration for the local POC."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

from poc.authentication import PocAuthStore


class PocSessionController:
    """Coordinate remembered authentication with mutable UI state."""

    def __init__(
        self,
        auth_store: PocAuthStore,
        session_state: MutableMapping[str, Any],
        query_params: MutableMapping[str, Any],
    ) -> None:
        """Bind existing state containers without reading persistence."""
        self._auth_store = auth_store
        self._session_state = session_state
        self._query_params = query_params

    def establish(self, user: dict[str, Any]) -> None:
        """Store the minimum authenticated user identity in UI state."""
        self._session_state["authenticated"] = True
        self._session_state["user"] = {
            key: user[key] for key in ("id", "email", "display_name", "role")
        }
        self._session_state["page"] = "nav_admin" if user["role"] == "admin" else "nav_home"

    def remember(self, user_id: str) -> str:
        """Create and return a persisted remembered-session token."""
        return self._auth_store.create_session(user_id)

    def restore(self) -> bool:
        """Restore a valid URL session and report whether it succeeded."""
        if self._session_state.get("authenticated"):
            return True
        session_id = self._query_params.get("sid")
        if isinstance(session_id, list):
            session_id = session_id[0] if session_id else ""
        if not session_id:
            return False
        user = self._auth_store.resolve_session(str(session_id))
        if not user:
            return False
        self.establish(user)
        return True

    def clear(self) -> None:
        """Revoke persistence and remove all user-specific UI state."""
        if user := self._session_state.get("user"):
            self._auth_store.revoke_session(str(user["id"]))
        for key in (
            "authenticated",
            "user",
            "show_login",
            "last_result",
            "last_inference_error",
            "smail_inbox",
            "smail_blocked",
            "page",
        ):
            self._session_state.pop(key, None)
        self._query_params.pop("sid", None)
