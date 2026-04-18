from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[4]
DEFAULT_DB_PATH = ROOT_DIR / "data/local/poc_test.db"
MANUAL_SOURCE_NAMES = (
    "cert-fr-cti",
    "phishtank-online-valid",
    "sap-labs-blog",
    "common-crawl-bigdata",
    "database-historical",
)
MANUAL_SOURCE_FILTER = (
    "name IN ('cert-fr-cti','phishtank-online-valid','sap-labs-blog',"
    "'common-crawl-bigdata','database-historical') OR name LIKE 'database/%'"
)


def _fetch_scalar(cursor: sqlite3.Cursor, query: str) -> int:
    return int(cursor.execute(query).fetchone()[0])


def _fetch_source_breakdown(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    rows = cursor.execute(
        f"""
        SELECT
            source.name AS source_name,
            source.source_type AS source_type,
            COUNT(DISTINCT record.id) AS raw_records,
            COUNT(DISTINCT message.id) AS normalized_messages
        FROM data_source_system AS source
        LEFT JOIN data_raw_record AS record ON record.source_system_id = source.id
        LEFT JOIN data_normalized_message AS message ON message.raw_record_id = record.id
        WHERE {MANUAL_SOURCE_FILTER}
        GROUP BY source.id
        ORDER BY raw_records DESC, source.name
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _fetch_latest_raw_object(
    cursor: sqlite3.Cursor, source_name: str
) -> dict[str, Any] | None:
    row = cursor.execute(
        """
        SELECT
            object.id,
            object.storage_uri,
            object.source_metadata,
            object.collected_at,
            run.raw_record_count,
            run.log_message
        FROM data_raw_object AS object
        JOIN data_ingestion_run AS run ON run.id = object.ingestion_run_id
        JOIN data_source_system AS source ON source.id = run.source_system_id
        WHERE source.name = ?
        ORDER BY object.created_at DESC
        LIMIT 1
        """,
        (source_name,),
    ).fetchone()
    if row is None:
        return None
    payload = dict(row)
    payload["source_metadata"] = json.loads(payload["source_metadata"])
    return payload


def _fetch_raw_content_source_breakdown(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    rows = cursor.execute(
        f"""
        SELECT
            json_extract(record.raw_content, '$.source') AS raw_source,
            COUNT(*) AS raw_count
        FROM data_raw_record AS record
        JOIN data_source_system AS source ON source.id = record.source_system_id
        WHERE {MANUAL_SOURCE_FILTER}
        GROUP BY raw_source
        ORDER BY raw_count DESC, raw_source
        LIMIT 25
        """
    ).fetchall()
    return [dict(row) for row in rows]


def _fetch_datasets(cursor: sqlite3.Cursor) -> list[dict[str, Any]]:
    rows = cursor.execute(
        """
        SELECT name, version_tag, status, item_count, frozen_at, created_at
        FROM data_dataset
        ORDER BY created_at
        """
    ).fetchall()
    return [dict(row) for row in rows]


def build_summary(db_path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    cursor = connection.cursor()

    summary = {
        "db_path": str(db_path),
        "totals": {
            "raw_objects": _fetch_scalar(
                cursor, "SELECT COUNT(*) FROM data_raw_object"
            ),
            "raw_records": _fetch_scalar(
                cursor, "SELECT COUNT(*) FROM data_raw_record"
            ),
            "normalized_messages": _fetch_scalar(
                cursor, "SELECT COUNT(*) FROM data_normalized_message"
            ),
            "annotations": _fetch_scalar(
                cursor, "SELECT COUNT(*) FROM data_annotation"
            ),
            "datasets": _fetch_scalar(cursor, "SELECT COUNT(*) FROM data_dataset"),
            "dataset_items": _fetch_scalar(
                cursor, "SELECT COUNT(*) FROM data_dataset_item"
            ),
        },
        "manual_source_breakdown": _fetch_source_breakdown(cursor),
        "latest_database_raw_object": _fetch_latest_raw_object(
            cursor, "database-historical"
        ),
        "latest_common_crawl_raw_object": _fetch_latest_raw_object(
            cursor, "common-crawl-bigdata"
        ),
        "raw_content_source_breakdown": _fetch_raw_content_source_breakdown(cursor),
        "datasets": _fetch_datasets(cursor),
    }
    connection.close()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Summarize poc_test.db validation state"
    )
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--output-json", type=Path, default=None)
    args = parser.parse_args()

    summary = build_summary(args.db_path)
    payload = json.dumps(summary, ensure_ascii=False, indent=2)
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(payload, encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()