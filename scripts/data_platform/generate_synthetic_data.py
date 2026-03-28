"""
Generate synthetic French emails from archetype templates.

Uses archetype JSON files in data/archetypes/ with Faker (fr_FR) and Jinja2-style
variable substitution to produce diverse, realistic synthetic emails.

Output follows the shared processing schema:
  text, label, source, language, archetype, text_len

Processing: shared backend preprocessing service

Usage:
  python scripts/generate_synthetic_data.py --class spam --count 10000
  python scripts/generate_synthetic_data.py --class legitimate --count 3000
  python scripts/generate_synthetic_data.py --class all
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from faker import Faker

# ── Add src to path so scripts share backend preprocessing logic ─────────────
BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / "src"))
from data_platform.services.preprocessing import (
    DataFramePreprocessingService,
    OUTPUT_COLS,
    save_processed_csv,
)

# ── Constants ────────────────────────────────────────────────
fake = Faker("fr_FR")
Faker.seed(42)
random.seed(42)

TODAY = date.today().strftime("%Y%m%d")
BASE = Path(__file__).resolve().parents[2]
ARCHETYPE_DIR = BASE / "data" / "archetypes"
PROC = BASE / "data" / "processed"
preprocessing_service = DataFramePreprocessingService()

# Default generation targets
DEFAULT_TARGETS: dict[str, int] = {
    "phishing": 7_500,  # 23 archetypes → target 7,500 synthetic phishing
    "spam": 10_000,  # 12 archetypes — already generated, skip unless re-run
    "legitimate": 5_000,  # 12 archetypes → target ~5,000 for 10K total legit
}


# ── Variable generation helpers ──────────────────────────────
def _gen_date_future(days_ahead: int = 30) -> str:
    """Generate a plausible future date string in French format."""
    d = date.today() + timedelta(days=random.randint(3, days_ahead))
    months_fr = [
        "",
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ]
    return f"{d.day} {months_fr[d.month]} {d.year}"


def _gen_date_past(days_back: int = 30) -> str:
    """Generate a plausible past date string in French format."""
    d = date.today() - timedelta(days=random.randint(1, days_back))
    months_fr = [
        "",
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ]
    return f"{d.day} {months_fr[d.month]} {d.year}"


def _resolve_variable(var_name: str, var_options: list[str] | None) -> str:
    """Resolve a single template variable to a concrete value."""
    # Special variables generated dynamically
    match var_name:
        case "prenom":
            return fake.first_name()
        case "nom":
            return fake.last_name()
        case "email":
            return fake.email()
        case "email_agent" | "email_exp" | "email_support" | "email_dpo":
            return fake.company_email()
        case "phone":
            return fake.phone_number()
        case "date" | "date_expiry" | "date_limite":
            return _gen_date_future()
        case "date_facture":
            return _gen_date_past()
        case "date_prochain" | "date_prelevement":
            return _gen_date_future(60)
        case "date_confirmation":
            return _gen_date_future(7)
        case "date_livraison":
            return _gen_date_future(10)
        case "date_expiration":
            d = date.today() + timedelta(days=random.randint(30, 180))
            return f"{d.month:02d}/{d.year}"
        case "adresse":
            return fake.address().replace("\n", ", ")
        case "ref":
            return f"REF-{random.randint(100000, 999999)}"
        case "sub_id":
            return str(random.randint(1000000, 9999999))
        case "tracking":
            prefix = random.choice(["8R", "CC", "6A", "9V", "FR"])
            return f"{prefix}{random.randint(10000000000, 99999999999)}"
        case "agent":
            return fake.name()
        case "annee":
            return str(random.choice([2025, 2026]))
        case "code":
            letters = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=3))
            return f"{letters}-{random.randint(1000, 9999)}-FR"
        case "iban":
            return f"FR76 {random.randint(1000,9999)} {random.randint(1000,9999)} {random.randint(1000,9999)} {random.randint(1000,9999)} {random.randint(1000,9999)} {random.randint(100,999)}"
        case "digits":
            return str(random.randint(1000, 9999))
        case "ville":
            return fake.city()
        case _:
            # Use provided options from archetype JSON
            if var_options:
                return random.choice(var_options)
            return f"[{var_name}]"


def render_template(template: str, variables: dict[str, list[str]]) -> str:
    """Render a template string by replacing {var} placeholders with values."""
    # Find all {variable_name} patterns
    pattern = re.compile(r"\{(\w+)\}")
    matches = pattern.findall(template)

    result = template
    # Track resolved values for consistency within one email
    resolved: dict[str, str] = {}

    for var_name in matches:
        if var_name not in resolved:
            var_options = variables.get(var_name)
            resolved[var_name] = _resolve_variable(var_name, var_options)
        # Replace first occurrence of this specific placeholder
        result = result.replace(f"{{{var_name}}}", resolved[var_name], 1)

    return result


# ── Core generation logic ────────────────────────────────────
def load_archetypes(class_name: str) -> dict:
    """Load archetype JSON for a given class."""
    path = ARCHETYPE_DIR / f"{class_name}_archetypes.json"
    if not path.exists():
        raise FileNotFoundError(f"Archetype file not found: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def generate_class(class_name: str, count: int) -> pd.DataFrame:
    """Generate `count` synthetic emails for a given class using archetypes."""
    data = load_archetypes(class_name)
    meta = data["meta"]
    label = meta["class_label"]
    archetypes = data["archetypes"]
    tier_dist = meta["tier_distribution"]

    # Build weighted archetype pool per tier
    tier_pools: dict[str, list[dict]] = {"simple": [], "medium": [], "hard": []}
    for arch in archetypes:
        tier = arch["tier"]
        weight = arch.get("weight", 1.0)
        # Add to pool with weight-based repetition (multiply by 10 for granularity)
        tier_pools[tier].extend([arch] * int(weight * 10))

    # Validate all tiers have archetypes
    for tier_name, pool in tier_pools.items():
        if not pool:
            print(f"  ⚠️  No archetypes for tier '{tier_name}' in {class_name}")

    # Compute per-tier counts
    tier_counts = {
        tier: max(1, int(count * frac))
        for tier, frac in tier_dist.items()
        if tier_pools.get(tier)
    }
    # Adjust to hit exact total
    diff = count - sum(tier_counts.values())
    if diff > 0:
        # Add remainder to the largest tier
        largest_tier = max(tier_counts, key=lambda k: tier_counts[k])
        tier_counts[largest_tier] += diff

    rows: list[dict] = []

    for tier, n in tier_counts.items():
        pool = tier_pools[tier]
        if not pool:
            continue

        for _ in range(n):
            arch = random.choice(pool)
            template = random.choice(arch["templates"])
            variables = arch.get("variables", {})

            text = render_template(template, variables)

            rows.append(
                {
                    "text": text,
                    "label": label,
                    "source": f"synthetic_{class_name}_{tier}",
                    "language": "fr",
                    "archetype": arch["id"],
                    "text_len": 0,  # Will be computed after cleaning
                }
            )

    df = pd.DataFrame(rows)
    print(
        f"  📝 Generated {len(df)} raw {class_name} emails "
        f"(simple={tier_counts.get('simple', 0)}, "
        f"medium={tier_counts.get('medium', 0)}, "
        f"hard={tier_counts.get('hard', 0)})"
    )

    return df


def generate_and_save(class_name: str, count: int) -> Path | None:
    """Generate, clean, deduplicate, and save synthetic data for a class."""
    if count <= 0:
        print(f"  ⏭️  Skipping {class_name} (count={count})")
        return None

    print(f"\n{'='*60}")
    print(f"  Generating {count} synthetic {class_name} emails...")
    print(f"{'='*60}")

    # Generate raw
    df = generate_class(class_name, count)

    # Process through the shared cleaning pipeline (clean + filter + dedup)
    processing_result = preprocessing_service.process_dataframe(df)
    df = processing_result.dataframe
    dropped_short = processing_result.dropped_short
    dropped_dup = processing_result.dropped_duplicate
    print(
        f"  🧹 After cleaning pipeline: {len(df)} rows "
        f"(dropped {dropped_short} short, {dropped_dup} duplicates)"
    )

    if df.empty:
        print(f"  ❌ No rows survived cleaning for {class_name}")
        return None

    # Determine output path based on class
    match class_name:
        case "phishing":
            out_dir = PROC / "phishing" / "synthetic_archetype"
        case "spam":
            out_dir = PROC / "spam" / "synthetic_spam"
        case "legitimate":
            out_dir = PROC / "legitimate" / "synthetic_archetype"
        case _:
            raise ValueError(f"Unknown class: {class_name}")

    filename = f"synth_{class_name}_clean_{len(df)}_{TODAY}.csv"
    out_path = out_dir / filename

    save_processed_csv(df, out_path)
    print(f"  ✅ Saved {out_path} ({len(df)} rows, {class_name})")
    return out_path


# ── Archetype distribution report ────────────────────────────
def print_archetype_report(path: Path) -> None:
    """Print archetype distribution for a generated CSV."""
    if not path or not path.exists():
        return
    df = pd.read_csv(path)
    print(f"\n  📊 Archetype distribution for {path.name}:")
    dist = df["archetype"].value_counts()
    for arch_raw, cnt in dist.items():
        arch = str(arch_raw)
        tier_tag = arch.split("_")[1] if "_" in arch else "?"
        print(f"     {arch:<40s} {cnt:>5d}  ({tier_tag})")
    print(f"     {'TOTAL':<40s} {len(df):>5d}")

    # Tier distribution
    tier_map = {}
    for arch_raw, cnt in dist.items():
        arch = str(arch_raw)
        parts = arch.split("_")
        tier = parts[1] if len(parts) > 1 else "unknown"
        tier_map[tier] = tier_map.get(tier, 0) + cnt
    print(f"\n  📈 Tier split:")
    for tier, cnt in sorted(tier_map.items()):
        print(f"     {tier:<10s} {cnt:>5d}  ({cnt/len(df)*100:.1f}%)")


# ── CLI ──────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate synthetic French emails from archetypes"
    )
    parser.add_argument(
        "--class",
        "-c",
        dest="cls",
        choices=["phishing", "spam", "legitimate", "all"],
        default="all",
        help="Which class to generate (default: all)",
    )
    parser.add_argument(
        "--count",
        "-n",
        type=int,
        default=0,
        help="Number of emails to generate (0 = use defaults)",
    )
    parser.add_argument(
        "--seed",
        "-s",
        type=int,
        default=42,
        help="Random seed for reproducibility",
    )
    args = parser.parse_args()

    # Set seeds
    random.seed(args.seed)
    Faker.seed(args.seed)

    classes = ["phishing", "spam", "legitimate"] if args.cls == "all" else [args.cls]

    print("=" * 60)
    print("  SICURRE — Synthetic Email Generator")
    print(f"  Date: {TODAY}")
    print(f"  Seed: {args.seed}")
    print("=" * 60)

    generated_files: list[tuple[str, Path | None]] = []

    for cls in classes:
        count = args.count if args.count > 0 else DEFAULT_TARGETS.get(cls, 0)
        path = generate_and_save(cls, count)
        generated_files.append((cls, path))

    # Summary
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    for cls, path in generated_files:
        if path and path.exists():
            df = pd.read_csv(path)
            print(f"  ✅ {cls:<12s} → {path.name} ({len(df)} rows)")
            print_archetype_report(path)
        else:
            print(f"  ⏭️  {cls:<12s} → skipped")

    print("\n  Done! 🎉")


if __name__ == "__main__":
    main()
