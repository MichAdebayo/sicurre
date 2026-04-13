from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path

import pandas as pd
from faker import Faker

from core.config import ROOT_DIR
from data_platform.services.preprocessing import (
    DataFramePreprocessingService,
    save_processed_csv,
)


TODAY = date.today().strftime("%Y%m%d")
ARCHETYPE_DIR = ROOT_DIR / "data" / "archetypes"
PROC = ROOT_DIR / "data" / "processed"
DEFAULT_TARGETS: dict[str, int] = {
    "phishing": 7_500,
    "spam": 10_000,
    "legitimate": 5_000,
}


@dataclass(frozen=True, slots=True)
class SyntheticGenerationResult:
    dataframe: pd.DataFrame
    class_name: str
    count: int
    output_path: Path | None


class SyntheticGenerationService:
    def __init__(self, *, seed: int = 42) -> None:
        self.seed = seed
        self.fake = Faker("fr_FR")
        self.preprocessing_service = DataFramePreprocessingService()
        self._set_seed(seed)

    def _set_seed(self, seed: int) -> None:
        random.seed(seed)
        Faker.seed(seed)

    def _gen_date_future(self, days_ahead: int = 30) -> str:
        target_date = date.today() + timedelta(days=random.randint(3, days_ahead))
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
        return f"{target_date.day} {months_fr[target_date.month]} {target_date.year}"

    def _gen_date_past(self, days_back: int = 30) -> str:
        target_date = date.today() - timedelta(days=random.randint(1, days_back))
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
        return f"{target_date.day} {months_fr[target_date.month]} {target_date.year}"

    def _resolve_variable(
        self,
        var_name: str,
        var_options: list[str] | None,
    ) -> str:
        match var_name:
            case "prenom":
                return self.fake.first_name()
            case "nom":
                return self.fake.last_name()
            case "email":
                return self.fake.email()
            case "email_agent" | "email_exp" | "email_support" | "email_dpo":
                return self.fake.company_email()
            case "phone":
                return self.fake.phone_number()
            case "date" | "date_expiry" | "date_limite":
                return self._gen_date_future()
            case "date_facture":
                return self._gen_date_past()
            case "date_prochain" | "date_prelevement":
                return self._gen_date_future(60)
            case "date_confirmation":
                return self._gen_date_future(7)
            case "date_livraison":
                return self._gen_date_future(10)
            case "date_expiration":
                target_date = date.today() + timedelta(days=random.randint(30, 180))
                return f"{target_date.month:02d}/{target_date.year}"
            case "adresse":
                return self.fake.address().replace("\n", ", ")
            case "ref":
                return f"REF-{random.randint(100000, 999999)}"
            case "sub_id":
                return str(random.randint(1000000, 9999999))
            case "tracking":
                prefix = random.choice(["8R", "CC", "6A", "9V", "FR"])
                return f"{prefix}{random.randint(10000000000, 99999999999)}"
            case "agent":
                return self.fake.name()
            case "annee":
                return str(random.choice([2025, 2026]))
            case "code":
                letters = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=3))
                return f"{letters}-{random.randint(1000, 9999)}-FR"
            case "iban":
                return (
                    f"FR76 {random.randint(1000,9999)} {random.randint(1000,9999)} "
                    f"{random.randint(1000,9999)} {random.randint(1000,9999)} "
                    f"{random.randint(1000,9999)} {random.randint(100,999)}"
                )
            case "digits":
                return str(random.randint(1000, 9999))
            case "ville":
                return self.fake.city()
            case _:
                if var_options:
                    return random.choice(var_options)
                return f"[{var_name}]"

    def render_template(self, template: str, variables: dict[str, list[str]]) -> str:
        pattern = re.compile(r"\{(\w+)\}")
        matches = pattern.findall(template)
        result = template
        resolved: dict[str, str] = {}

        for var_name in matches:
            if var_name not in resolved:
                resolved[var_name] = self._resolve_variable(
                    var_name,
                    variables.get(var_name),
                )
            result = result.replace(f"{{{var_name}}}", resolved[var_name], 1)

        return result

    def load_archetypes(self, class_name: str) -> dict:
        path = ARCHETYPE_DIR / f"{class_name}_archetypes.json"
        if not path.exists():
            raise FileNotFoundError(f"Archetype file not found: {path}")
        return json.loads(path.read_text(encoding="utf-8"))

    def generate_class(self, class_name: str, count: int) -> pd.DataFrame:
        data = self.load_archetypes(class_name)
        meta = data["meta"]
        label = meta["class_label"]
        archetypes = data["archetypes"]
        tier_dist = meta["tier_distribution"]

        tier_pools: dict[str, list[dict]] = {"simple": [], "medium": [], "hard": []}
        for archetype in archetypes:
            tier = archetype["tier"]
            weight = archetype.get("weight", 1.0)
            tier_pools[tier].extend([archetype] * int(weight * 10))

        tier_counts = {
            tier: max(1, int(count * fraction))
            for tier, fraction in tier_dist.items()
            if tier_pools.get(tier)
        }
        difference = count - sum(tier_counts.values())
        if difference > 0:
            largest_tier = max(tier_counts, key=lambda item: tier_counts[item])
            tier_counts[largest_tier] += difference

        rows: list[dict[str, object]] = []
        for tier, row_count in tier_counts.items():
            pool = tier_pools[tier]
            if not pool:
                continue
            for _ in range(row_count):
                archetype = random.choice(pool)
                template = random.choice(archetype["templates"])
                text = self.render_template(template, archetype.get("variables", {}))
                rows.append(
                    {
                        "text": text,
                        "label": label,
                        "source": f"synthetic_{class_name}_{tier}",
                        "language": "fr",
                        "archetype": archetype["id"],
                        "text_len": 0,
                    }
                )

        return pd.DataFrame(rows)

    def generate_cleaned_class(self, class_name: str, count: int) -> pd.DataFrame:
        dataframe = self.generate_class(class_name, count)
        processing_result = self.preprocessing_service.process_dataframe(dataframe)
        return processing_result.dataframe.reset_index(drop=True)

    def add_text_hashes(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        output_df = dataframe.copy()
        output_df["text_hash"] = output_df["text"].astype(str).apply(
            lambda value: sha256(value.encode("utf-8")).hexdigest()
        )
        return output_df

    def generate_and_save(self, class_name: str, count: int) -> Path | None:
        if count <= 0:
            print(f"  ⏭️  Skipping {class_name} (count={count})")
            return None

        print(f"\n{'='*60}")
        print(f"  Generating {count} synthetic {class_name} emails...")
        print(f"{'='*60}")

        dataframe = self.generate_class(class_name, count)
        processing_result = self.preprocessing_service.process_dataframe(dataframe)
        cleaned_df = self.add_text_hashes(processing_result.dataframe)
        print(
            f"  🧹 After cleaning pipeline: {len(cleaned_df)} rows "
            f"(dropped {processing_result.dropped_short} short, "
            f"{processing_result.dropped_duplicate} duplicates)"
        )

        if cleaned_df.empty:
            print(f"  ❌ No rows survived cleaning for {class_name}")
            return None

        out_path = self.save_generated_dataframe(class_name, cleaned_df)
        print(f"  ✅ Saved {out_path} ({len(cleaned_df)} rows, {class_name})")
        return out_path

    def save_generated_dataframe(self, class_name: str, dataframe: pd.DataFrame) -> Path:
        cleaned_df = self.add_text_hashes(dataframe)

        match class_name:
            case "phishing":
                out_dir = PROC / "phishing" / "synthetic_archetype"
            case "spam":
                out_dir = PROC / "spam" / "synthetic_spam"
            case "legitimate":
                out_dir = PROC / "legitimate" / "synthetic_archetype"
            case _:
                raise ValueError(f"Unknown class: {class_name}")

        out_path = out_dir / f"synth_{class_name}_clean_{len(cleaned_df)}_{TODAY}.csv"
        save_processed_csv(cleaned_df, out_path)
        return out_path

    def generate_result(
        self,
        class_name: str,
        count: int,
        *,
        export: bool = True,
    ) -> SyntheticGenerationResult:
        if count <= 0:
            return SyntheticGenerationResult(
                dataframe=pd.DataFrame(),
                class_name=class_name,
                count=count,
                output_path=None,
            )

        cleaned_df = self.add_text_hashes(self.generate_cleaned_class(class_name, count))
        output_path = (
            self.save_generated_dataframe(class_name, cleaned_df) if export else None
        )
        return SyntheticGenerationResult(
            dataframe=cleaned_df,
            class_name=class_name,
            count=count,
            output_path=output_path,
        )

    def print_archetype_report(self, path: Path) -> None:
        if not path.exists():
            return
        dataframe = pd.read_csv(path)
        print(f"\n  📊 Archetype distribution for {path.name}:")
        distribution = dataframe["archetype"].value_counts()
        for archetype_raw, count in distribution.items():
            archetype = str(archetype_raw)
            tier_tag = archetype.split("_")[1] if "_" in archetype else "?"
            print(f"     {archetype:<40s} {count:>5d}  ({tier_tag})")
        print(f"     {'TOTAL':<40s} {len(dataframe):>5d}")

        tier_map: dict[str, int] = {}
        for archetype_raw, count in distribution.items():
            archetype = str(archetype_raw)
            parts = archetype.split("_")
            tier = parts[1] if len(parts) > 1 else "unknown"
            tier_map[tier] = tier_map.get(tier, 0) + count
        print("\n  📈 Tier split:")
        for tier, count in sorted(tier_map.items()):
            print(f"     {tier:<10s} {count:>5d}  ({count/len(dataframe)*100:.1f}%)")
