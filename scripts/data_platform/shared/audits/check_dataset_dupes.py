"""
Check for duplicate content in data_dataset_item.

Checks:
  1. Item counts per split
  2. SHA256 duplicates within the dataset
  3. Exact-text duplicates (content dedup beyond SHA)
  4. Cross-split leakage (same text in train+val or train+test)
  5. Near-duplicate count by label (same text, different labels)
"""

import sqlite3
from pathlib import Path

DB = Path(__file__).parents[2] / "data" / "local" / "sicurre.db"
con = sqlite3.connect(DB)
cur = con.cursor()

SEP = "=" * 65

# ── 1. Counts per split ───────────────────────────────────────────────
print(SEP)
print("1. Dataset item counts per split")
print(SEP)
cur.execute("""
    SELECT i.split_name, COUNT(*) AS total
    FROM data_dataset_item i
    GROUP BY i.split_name
    ORDER BY i.split_name
""")
total = 0
for r in cur.fetchall():
    print(f"  {r[0]:10s}  {r[1]:>7,}")
    total += r[1]
print(f"  {'TOTAL':10s}  {total:>7,}")

# ── 2. SHA256 duplicates within dataset items ─────────────────────────
print()
print(SEP)
print("2. SHA256 duplicates (same hash, multiple dataset_item rows)")
print(SEP)
cur.execute("""
    SELECT nm.text_sha256, nm.current_label, COUNT(*) AS n
    FROM data_dataset_item di
    JOIN data_normalized_message nm ON nm.id = di.normalized_message_id
    GROUP BY nm.text_sha256
    HAVING COUNT(*) > 1
    ORDER BY n DESC
    LIMIT 50
""")
sha_dupes = cur.fetchall()
print(f"  Duplicate SHA groups : {len(sha_dupes)}")
cur.execute("""
    SELECT COALESCE(SUM(n - 1), 0) FROM (
        SELECT COUNT(*) AS n
        FROM data_dataset_item di
        JOIN data_normalized_message nm ON nm.id = di.normalized_message_id
        GROUP BY nm.text_sha256
        HAVING COUNT(*) > 1
    )
""")
extra_sha = cur.fetchone()[0]
print(f"  Extra rows (would be removed by SHA dedup) : {extra_sha:,}")
if sha_dupes:
    print("  Top 10:")
    for r in sha_dupes[:10]:
        print(f"    sha={r[0][:20]}...  label={r[1]:12s}  count={r[2]}")

# ── 3. Exact-text duplicates (independent of SHA) ────────────────────
print()
print(SEP)
print("3. Exact-text duplicates (same normalized_text, multiple items)")
print(SEP)
cur.execute("""
    SELECT nm.normalized_text, nm.current_label, COUNT(*) AS n
    FROM data_dataset_item di
    JOIN data_normalized_message nm ON nm.id = di.normalized_message_id
    GROUP BY nm.normalized_text
    HAVING COUNT(*) > 1
    ORDER BY n DESC
    LIMIT 50
""")
text_dupes = cur.fetchall()
print(f"  Duplicate text groups : {len(text_dupes)}")
cur.execute("""
    SELECT COALESCE(SUM(n - 1), 0) FROM (
        SELECT COUNT(*) AS n
        FROM data_dataset_item di
        JOIN data_normalized_message nm ON nm.id = di.normalized_message_id
        GROUP BY nm.normalized_text
        HAVING COUNT(*) > 1
    )
""")
extra_text = cur.fetchone()[0]
print(f"  Extra rows (would be removed by text dedup) : {extra_text:,}")
if text_dupes:
    print("  Top 10 (preview):")
    for r in text_dupes[:10]:
        preview = r[0][:90].replace("\n", " ") if r[0] else ""
        print(f"    count={r[2]}  label={r[1]:12s}  text={preview!r}")

# ── 4. Cross-split leakage ────────────────────────────────────────────
print()
print(SEP)
print("4. Cross-split leakage (same SHA in more than one split)")
print(SEP)
cur.execute("""
    SELECT nm.text_sha256, GROUP_CONCAT(DISTINCT di.split_name) AS splits,
           COUNT(*) AS n
    FROM data_dataset_item di
    JOIN data_normalized_message nm ON nm.id = di.normalized_message_id
    GROUP BY nm.text_sha256
    HAVING COUNT(DISTINCT di.split_name) > 1
    ORDER BY n DESC
    LIMIT 50
""")
leakage = cur.fetchall()
print(f"  Cross-split leaks : {len(leakage)}")
if leakage:
    print("  Top 10:")
    for r in leakage[:10]:
        print(f"    sha={r[0][:20]}...  splits={r[1]}  rows={r[2]}")

# ── 5. Label conflicts (same text, different labels) ─────────────────
print()
print(SEP)
print("5. Label conflicts (same text, different current_label values)")
print(SEP)
cur.execute("""
    SELECT nm.normalized_text,
           GROUP_CONCAT(DISTINCT nm.current_label) AS labels,
           COUNT(DISTINCT nm.current_label) AS n_labels,
           COUNT(*) AS n_items
    FROM data_dataset_item di
    JOIN data_normalized_message nm ON nm.id = di.normalized_message_id
    GROUP BY nm.normalized_text
    HAVING COUNT(DISTINCT nm.current_label) > 1
    ORDER BY n_items DESC
    LIMIT 20
""")
conflicts = cur.fetchall()
print(f"  Label conflict groups : {len(conflicts)}")
if conflicts:
    print("  Top 10:")
    for r in conflicts[:10]:
        preview = r[0][:80].replace("\n", " ") if r[0] else ""
        print(f"    labels={r[1]}  items={r[3]}  text={preview!r}")

# ── 6. By-label breakdown of duplicates ──────────────────────────────
print()
print(SEP)
print("6. Duplicate SHA distribution by label")
print(SEP)
cur.execute("""
    SELECT nm.current_label, COUNT(*) AS dup_groups, SUM(n - 1) AS extra_rows
    FROM (
        SELECT nm.current_label, COUNT(*) AS n
        FROM data_dataset_item di
        JOIN data_normalized_message nm ON nm.id = di.normalized_message_id
        GROUP BY nm.text_sha256
        HAVING COUNT(*) > 1
    ) sub
    JOIN data_normalized_message nm ON 1=1  -- just to get label name in outer
    GROUP BY nm.current_label
""")
# simpler version
cur.execute("""
    SELECT sub.current_label, COUNT(*) AS dup_groups, SUM(sub.n - 1) AS extra_rows
    FROM (
        SELECT nm.current_label, COUNT(*) AS n
        FROM data_dataset_item di
        JOIN data_normalized_message nm ON nm.id = di.normalized_message_id
        GROUP BY nm.text_sha256, nm.current_label
        HAVING COUNT(*) > 1
    ) sub
    GROUP BY sub.current_label
    ORDER BY extra_rows DESC
""")
for r in cur.fetchall():
    print(f"  label={r[0]:12s}  dup_groups={r[1]:>5,}  extra_rows={r[2]:>5,}")

con.close()
print()
print("Done.")
