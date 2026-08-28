"""Tenant-scoped inference evidence persistence for the local POC."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from poc.authentication import PocAuthStore
from poc.presentation.formatting import safe_text


class PocEventStore:
    """Persist and retrieve local evidence with mandatory user scoping."""

    def __init__(self, auth_store: PocAuthStore) -> None:
        """Inject persistence without opening a connection."""
        self._auth_store = auth_store

    def record(
        self,
        *,
        user_email: str,
        context: str,
        subject: str,
        sender: str,
        text_value: str,
        result: dict[str, Any],
        delivered_in_smail: bool,
        expected_label: str | None,
    ) -> None:
        """Store bounded classification evidence without a raw email body."""
        params = result.get("params") or {}
        self._auth_store.execute(
            """
            INSERT INTO app_inference_event (
                id, created_at, user_email, context, subject, sender, snippet,
                safety_verdict, label_verdict, composite_score, is_phishing,
                delivered_in_smail, llm_provider, explanation, latency_ms,
                used_llm, used_virustotal, inference_source, stage_scores_json,
                stage_labels_json, stage_breakdown_json, expected_label
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                datetime.now(UTC).isoformat(),
                user_email,
                context,
                subject,
                sender,
                safe_text(text_value, 240),
                result["safety_verdict"],
                result["label_verdict"],
                result["composite_score"],
                int(bool(result["is_phishing"])),
                int(delivered_in_smail),
                result.get("llm_provider", "n/a"),
                result.get("explanation", ""),
                float(result.get("latency_ms") or 0.0),
                int(bool(params.get("use_llm"))),
                int(bool(params.get("use_virustotal"))),
                str(result.get("source") or "api"),
                json.dumps(result.get("stage_scores") or {}, ensure_ascii=True),
                json.dumps(result.get("stage_labels") or {}, ensure_ascii=True),
                json.dumps(result.get("stage_breakdown") or {}, ensure_ascii=True),
                expected_label,
            ),
        )

    def reclassify(self, event_id: str, new_verdict: str, user_email: str) -> bool:
        """Override only an event owned by the authenticated local user."""
        if new_verdict not in {"safe", "phishing"}:
            raise ValueError("Unsupported remediation verdict.")
        before = self._auth_store.query(
            "SELECT id FROM app_inference_event WHERE id = ? AND user_email = ?",
            (event_id, user_email),
        )
        if not before:
            return False
        self._auth_store.execute(
            """
            UPDATE app_inference_event
            SET override_verdict = ?, override_by = ?, overridden_at = ?
            WHERE id = ? AND user_email = ?
            """,
            (
                new_verdict,
                user_email,
                datetime.now(UTC).isoformat(),
                event_id,
                user_email,
            ),
        )
        return True

    def delete(self, event_id: str, user_email: str) -> bool:
        """Permanently delete one event owned by the authenticated local user."""
        before = self._auth_store.query(
            "SELECT id FROM app_inference_event WHERE id = ? AND user_email = ?",
            (event_id, user_email),
        )
        if not before:
            return False
        self._auth_store.execute(
            "DELETE FROM app_inference_event WHERE id = ? AND user_email = ?",
            (event_id, user_email),
        )
        return True

    def list_for_user(self, user_email: str, limit: int = 500) -> list[dict[str, Any]]:
        """Return newest evidence owned by one local user."""
        rows = self._auth_store.query(
            """
            SELECT id, created_at, user_email, context, subject, sender, snippet,
                   safety_verdict, label_verdict, composite_score, is_phishing,
                   delivered_in_smail, llm_provider, explanation, latency_ms,
                   used_llm, used_virustotal, inference_source, stage_scores_json,
                   stage_labels_json, stage_breakdown_json, expected_label,
                   override_verdict, override_by, overridden_at
            FROM app_inference_event
            WHERE user_email = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_email, limit),
        )
        events: list[dict[str, Any]] = []
        for row in rows:
            event = dict(row)
            event["stage_scores"] = json.loads(event.pop("stage_scores_json") or "{}")
            event["stage_labels"] = json.loads(event.pop("stage_labels_json") or "{}")
            event["stage_breakdown"] = json.loads(event.pop("stage_breakdown_json") or "{}")
            for field in ("is_phishing", "delivered_in_smail", "used_llm", "used_virustotal"):
                event[field] = bool(event[field])
            events.append(event)
        return events
