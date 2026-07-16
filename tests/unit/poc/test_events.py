"""Tenant-isolation tests for local POC inference evidence."""

import sqlite3
from pathlib import Path

import pytest

from poc.authentication import PocAuthStore
from poc.events import PocEventStore


def event_store(database_path: Path) -> PocEventStore:
    """Create the isolated inference-event schema used by the repository."""
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE app_inference_event (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, user_email TEXT NOT NULL,
            context TEXT NOT NULL, subject TEXT NOT NULL, sender TEXT NOT NULL,
            snippet TEXT NOT NULL, safety_verdict TEXT NOT NULL,
            label_verdict TEXT NOT NULL, composite_score REAL NOT NULL,
            is_phishing INTEGER NOT NULL, delivered_in_smail INTEGER NOT NULL,
            llm_provider TEXT NOT NULL, explanation TEXT NOT NULL,
            latency_ms REAL NOT NULL, used_llm INTEGER NOT NULL,
            used_virustotal INTEGER NOT NULL, inference_source TEXT NOT NULL,
            stage_scores_json TEXT NOT NULL, stage_labels_json TEXT NOT NULL,
            stage_breakdown_json TEXT NOT NULL, expected_label TEXT,
            override_verdict TEXT, override_by TEXT, overridden_at TEXT
        )
        """
    )
    connection.commit()
    connection.close()
    return PocEventStore(PocAuthStore(database_path))


def result() -> dict[str, object]:
    """Return representative inference evidence."""
    return {
        "safety_verdict": "phishing",
        "label_verdict": "phishing",
        "composite_score": 0.98,
        "is_phishing": True,
        "llm_provider": "none",
        "explanation": "Suspicious request",
        "latency_ms": 42,
        "source": "simulation",
        "params": {"use_llm": False, "use_virustotal": False},
        "stage_scores": {"model": 0.98},
        "stage_labels": {"model": "phishing"},
        "stage_breakdown": {},
    }


def record(store: PocEventStore, user_email: str, subject: str) -> None:
    """Persist one bounded event for a local user."""
    store.record(
        user_email=user_email,
        context="playground",
        subject=subject,
        sender="sender@example.test",
        text_value="body " * 100,
        result=result(),
        delivered_in_smail=False,
        expected_label="phishing",
    )


def test_events_are_listed_only_for_the_authenticated_user(tmp_path: Path) -> None:
    """One local account cannot read another account's evidence."""
    store = event_store(tmp_path / "events.db")
    record(store, "alice@example.test", "Alice event")
    record(store, "bob@example.test", "Bob event")

    alice_events = store.list_for_user("alice@example.test")
    assert [event["subject"] for event in alice_events] == ["Alice event"]
    assert len(alice_events[0]["snippet"]) <= 243
    assert alice_events[0]["is_phishing"] is True


def test_reclassification_is_tenant_scoped_and_validated(tmp_path: Path) -> None:
    """Cross-user remediation is a no-op and unsupported verdicts are rejected."""
    store = event_store(tmp_path / "events.db")
    record(store, "alice@example.test", "Alice event")
    event_id = str(store.list_for_user("alice@example.test")[0]["id"])

    assert not store.reclassify(event_id, "safe", "bob@example.test")
    assert store.reclassify(event_id, "safe", "alice@example.test")
    assert store.list_for_user("alice@example.test")[0]["override_verdict"] == "safe"
    with pytest.raises(ValueError, match="Unsupported remediation verdict"):
        store.reclassify(event_id, "spam", "alice@example.test")
