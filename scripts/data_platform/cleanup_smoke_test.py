"""
One-shot cleanup script: remove the Apr 13 smoke-test generation data.

Deletes:
  - 2 generation runs (adapted smoke + synthetic smoke) → 11 samples
  - 11 promoted raw_records + 11 normalized_messages + 11 annotations
  - 2 processing runs (generate_cli_smoke_20260413)
  - 2 ingestion runs + raw_objects for smoke source systems
  - 2 smoke source systems (synthetic-generated-adapted-..., synthetic-generated-synthetic-...)

Preserves:
  - CertFR generation run (9 samples, generation_gated_promotion_v1)
  - All 1.3.0 pipeline data (10,188 normalized messages)
  - All raw_record data (172K+ records)
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "local" / "sicurre.db"

# IDs gathered from the audit
SMOKE_GENERATION_RUN_IDS = [
    "5bd59bd6757749039c23be48e8e5b3e3",  # adapted_phishing_generator/adapted_en_fr
    "919d1462a81c49619e44e2d87b200a00",  # synthetic_archetype_generator/synthetic_phishing_archetype
]

SMOKE_PROCESSING_RUN_IDS = [
    "23090415e65c4509a46dee7d0e5ede86",  # generate_cli_smoke_20260413 (1)
    "f987ecd1c2d241a1aec5709db08e3f7a",  # generate_cli_smoke_20260413 (2)
]

SMOKE_INGESTION_RUN_IDS = [
    "caf004f72a5a",  # adapted source system
    "3eb8161906e0",  # synthetic source system
]

SMOKE_SOURCE_SYSTEM_NAMES = [
    "synthetic-generated-adapted-phishing-generator-adapted-en-fr",
    "synthetic-generated-synthetic-archetype-generator-synthetic-phishing-archetype",
]


def main() -> None:
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = OFF")
    cur = conn.cursor()

    print("=== PHASE 1: Cleaning smoke test data ===\n")

    # 1. Delete annotations for smoke normalized messages
    cur.execute("""
        DELETE FROM data_annotation 
        WHERE normalized_message_id IN (
            SELECT id FROM data_normalized_message 
            WHERE processing_run_id IN (?, ?)
        )
    """, SMOKE_PROCESSING_RUN_IDS)
    print(f"  Deleted {cur.rowcount} smoke annotations")

    # 2. Delete smoke normalized messages
    cur.execute("""
        DELETE FROM data_normalized_message 
        WHERE processing_run_id IN (?, ?)
    """, SMOKE_PROCESSING_RUN_IDS)
    print(f"  Deleted {cur.rowcount} smoke normalized messages")

    # 3. Delete smoke processing runs
    cur.execute("""
        DELETE FROM data_processing_run 
        WHERE id IN (?, ?)
    """, SMOKE_PROCESSING_RUN_IDS)
    print(f"  Deleted {cur.rowcount} smoke processing runs")

    # 4. Delete data_generation_sample_source_link for smoke samples
    cur.execute("""
        DELETE FROM data_generation_sample_source_link 
        WHERE generation_sample_id IN (
            SELECT id FROM data_generation_sample 
            WHERE generation_run_id IN (?, ?)
        )
    """, SMOKE_GENERATION_RUN_IDS)
    print(f"  Deleted {cur.rowcount} smoke source links")

    # 5. Null out generation_sample_id on promoted raw_records (before deleting samples)
    cur.execute("""
        UPDATE data_raw_record 
        SET generation_sample_id = NULL
        WHERE generation_sample_id IN (
            SELECT id FROM data_generation_sample 
            WHERE generation_run_id IN (?, ?)
        )
    """, SMOKE_GENERATION_RUN_IDS)
    print(f"  Cleared generation_sample_id on {cur.rowcount} promoted raw records")

    # 6. Delete promoted raw_records for smoke source systems
    for source_name in SMOKE_SOURCE_SYSTEM_NAMES:
        cur.execute("""
            DELETE FROM data_raw_record 
            WHERE source_system_id IN (
                SELECT id FROM data_source_system WHERE name = ?
            )
        """, (source_name,))
        print(f"  Deleted {cur.rowcount} promoted raw records for {source_name}")

    # 7. Delete raw_objects for smoke ingestion runs
    for ingestion_id_prefix in SMOKE_INGESTION_RUN_IDS:
        cur.execute("""
            DELETE FROM data_raw_object 
            WHERE ingestion_run_id IN (
                SELECT id FROM data_ingestion_run WHERE id LIKE ?
            )
        """, (ingestion_id_prefix + "%",))
        print(f"  Deleted {cur.rowcount} raw objects for ingestion {ingestion_id_prefix}")

    # 8. Delete smoke ingestion runs
    for ingestion_id_prefix in SMOKE_INGESTION_RUN_IDS:
        cur.execute("""
            DELETE FROM data_ingestion_run WHERE id LIKE ?
        """, (ingestion_id_prefix + "%",))
        print(f"  Deleted {cur.rowcount} smoke ingestion runs ({ingestion_id_prefix})")

    # 9. Delete smoke generation samples
    cur.execute("""
        DELETE FROM data_generation_sample 
        WHERE generation_run_id IN (?, ?)
    """, SMOKE_GENERATION_RUN_IDS)
    print(f"  Deleted {cur.rowcount} smoke generation samples")

    # 10. Delete smoke generation runs
    cur.execute("""
        DELETE FROM data_generation_run 
        WHERE id IN (?, ?)
    """, SMOKE_GENERATION_RUN_IDS)
    print(f"  Deleted {cur.rowcount} smoke generation runs")

    # 11. Delete smoke source systems (they're now empty)
    for source_name in SMOKE_SOURCE_SYSTEM_NAMES:
        cur.execute("DELETE FROM data_source_system WHERE name = ?", (source_name,))
        print(f"  Deleted {cur.rowcount} source system: {source_name}")

    conn.commit()

    # Verify final state
    print("\n=== POST-CLEANUP VERIFICATION ===\n")
    cur.execute("SELECT COUNT(*) FROM data_generation_run")
    print(f"  Generation runs: {cur.fetchone()[0]} (expected: 1 — CertFR)")
    cur.execute("SELECT COUNT(*) FROM data_generation_sample")
    print(f"  Generation samples: {cur.fetchone()[0]} (expected: 9 — CertFR)")
    cur.execute("SELECT pipeline_version, COUNT(*) FROM data_processing_run GROUP BY pipeline_version")
    print(f"  Processing runs: {dict(cur.fetchall())}")
    cur.execute("SELECT COUNT(*) FROM data_normalized_message")
    print(f"  Normalized messages: {cur.fetchone()[0]} (expected: 10,197 = 10,188 + 9)")
    cur.execute("SELECT current_label, COUNT(*) FROM data_normalized_message GROUP BY current_label")
    print(f"  Label distribution: {dict(cur.fetchall())}")
    cur.execute("SELECT label_source, COUNT(*) FROM data_annotation GROUP BY label_source")
    print(f"  Annotations: {dict(cur.fetchall())}")
    cur.execute("SELECT COUNT(*) FROM data_raw_record WHERE generation_sample_id IS NOT NULL")
    print(f"  Promoted raw records: {cur.fetchone()[0]} (expected: 9 — CertFR)")
    cur.execute("SELECT name FROM data_source_system WHERE name LIKE 'synthetic-generated-%'")
    remaining_synth = [r[0] for r in cur.fetchall()]
    print(f"  Remaining synthetic sources: {remaining_synth}")

    conn.close()
    print("\n✅ Cleanup complete.")


if __name__ == "__main__":
    main()
