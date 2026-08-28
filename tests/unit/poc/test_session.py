"""Tests for local POC session state orchestration."""

from unittest.mock import Mock

from poc.session import PocSessionController


def test_session_restore_and_clear_are_explicit() -> None:
    """Remembered identity restores minimal state and logout revokes it."""
    store = Mock()
    store.resolve_session.return_value = {
        "id": "user-1",
        "email": "user@example.test",
        "display_name": "User",
        "role": "viewer",
        "password_hash": "not-copied",
    }
    state: dict[str, object] = {}
    query: dict[str, object] = {"sid": ["remembered-token"]}
    controller = PocSessionController(store, state, query)

    assert controller.restore()
    assert state["user"] == {
        "id": "user-1",
        "email": "user@example.test",
        "display_name": "User",
        "role": "viewer",
    }
    assert state["page"] == "nav_home"
    store.resolve_session.assert_called_once_with("remembered-token")

    controller.clear()
    store.revoke_session.assert_called_once_with("user-1")
    assert "user" not in state
    assert "sid" not in query
    assert "page" not in state


def test_administrator_session_opens_the_administration_overview() -> None:
    """An administrator enters the distinct aggregate platform surface."""
    store = Mock()
    state: dict[str, object] = {"page": "nav_home"}
    controller = PocSessionController(store, state, {})
    controller.establish(
        {
            "id": "admin-1",
            "email": "admin@example.test",
            "display_name": "Admin",
            "role": "admin",
        }
    )
    assert state["page"] == "nav_admin"


def test_session_without_token_does_not_query_persistence() -> None:
    """Anonymous startup has no persistence side effect."""
    store = Mock()
    controller = PocSessionController(store, {}, {})
    assert not controller.restore()
    store.resolve_session.assert_not_called()
