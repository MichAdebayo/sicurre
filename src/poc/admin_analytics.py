"""Aggregate, content-free administration evidence for the local POC."""

from __future__ import annotations

from dataclasses import dataclass

from poc.authentication import PocAuthStore
from poc.data_evidence import PocDataEvidenceStore


@dataclass(frozen=True)
class AccountActivity:
    """Bounded account activity visible to a POC administrator."""

    display_name: str
    email: str
    role: str
    last_login_at: str | None
    event_count: int


@dataclass(frozen=True)
class ClassificationTotals:
    """Aggregate effective classifications across local POC accounts."""

    total: int
    legitimate: int
    spam: int
    phishing: int
    corrections: int


@dataclass(frozen=True)
class DataPlatformState:
    """Current local data-platform grain without record-level content."""

    raw_records: int
    normalized_messages: int
    dataset_items: int
    dataset_version: str | None
    dataset_status: str | None
    latest_ingestion_at: str | None


@dataclass(frozen=True)
class AdminSnapshot:
    """Complete content-free administration snapshot."""

    accounts: tuple[AccountActivity, ...]
    classifications: ClassificationTotals
    data_platform: DataPlatformState


class PocAdminAnalytics:
    """Build read-only aggregate evidence across the isolated POC stores."""

    def __init__(
        self,
        auth_store: PocAuthStore,
        data_store: PocDataEvidenceStore,
    ) -> None:
        """Inject the local stores without opening either database."""
        self._auth_store = auth_store
        self._data_store = data_store

    def snapshot(self) -> AdminSnapshot:
        """Return the current aggregate administration state."""
        return AdminSnapshot(
            accounts=self._account_activity(),
            classifications=self._classification_totals(),
            data_platform=self._data_platform_state(),
        )

    def _account_activity(self) -> tuple[AccountActivity, ...]:
        rows = self._auth_store.query(
            """
            SELECT u.display_name, u.email, u.role, u.last_login_at,
                   COUNT(e.id) AS event_count
            FROM poc_user u
            LEFT JOIN app_inference_event e ON e.user_email = u.email
            GROUP BY u.id
            ORDER BY CASE u.role WHEN 'admin' THEN 0 ELSE 1 END, u.email
            """
        )
        return tuple(
            AccountActivity(
                display_name=str(row["display_name"]),
                email=str(row["email"]),
                role=str(row["role"]),
                last_login_at=str(row["last_login_at"]) if row["last_login_at"] else None,
                event_count=int(row["event_count"]),
            )
            for row in rows
        )

    def _classification_totals(self) -> ClassificationTotals:
        rows = self._auth_store.query(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN COALESCE(override_verdict, safety_verdict) = 'phishing'
                            THEN 1 ELSE 0 END) AS phishing,
                   SUM(CASE WHEN COALESCE(override_verdict, safety_verdict) = 'safe'
                                 AND label_verdict = 'spam' THEN 1 ELSE 0 END) AS spam,
                   SUM(CASE WHEN COALESCE(override_verdict, safety_verdict) = 'safe'
                                 AND label_verdict != 'spam' THEN 1 ELSE 0 END) AS legitimate,
                   SUM(CASE WHEN overridden_at IS NOT NULL THEN 1 ELSE 0 END) AS corrections
            FROM app_inference_event
            """
        )
        row = rows[0]
        return ClassificationTotals(
            total=int(row["total"] or 0),
            legitimate=int(row["legitimate"] or 0),
            spam=int(row["spam"] or 0),
            phishing=int(row["phishing"] or 0),
            corrections=int(row["corrections"] or 0),
        )

    def _data_platform_state(self) -> DataPlatformState:
        latest_dataset = self._latest_dataset()
        return DataPlatformState(
            raw_records=self._data_store.count("data_raw_record"),
            normalized_messages=self._data_store.count("data_normalized_message"),
            dataset_items=int(latest_dataset.get("item_count") or 0),
            dataset_version=_optional_text(latest_dataset.get("version_tag")),
            dataset_status=_optional_text(latest_dataset.get("status")),
            latest_ingestion_at=self._latest_ingestion_at(),
        )

    def _latest_dataset(self) -> dict[str, object]:
        if not self._data_store.table_exists("data_dataset"):
            return {}
        rows = self._data_store.query(
            """
            SELECT d.version_tag, d.status, COUNT(di.id) AS item_count
            FROM data_dataset d
            LEFT JOIN data_dataset_item di ON di.dataset_id = d.id
            GROUP BY d.id
            ORDER BY datetime(d.created_at) DESC
            LIMIT 1
            """
        )
        return rows[0] if rows else {}

    def _latest_ingestion_at(self) -> str | None:
        if not self._data_store.table_exists("data_ingestion_run"):
            return None
        rows = self._data_store.query(
            """
            SELECT COALESCE(finished_at, started_at) AS observed_at
            FROM data_ingestion_run
            ORDER BY datetime(COALESCE(finished_at, started_at)) DESC
            LIMIT 1
            """
        )
        return _optional_text(rows[0].get("observed_at")) if rows else None


def _optional_text(value: object) -> str | None:
    """Normalize an optional database value for presentation."""
    normalized = str(value or "").strip()
    return normalized or None
