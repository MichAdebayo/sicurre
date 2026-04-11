from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pandas as pd

from core.config import ROOT_DIR
from data_platform.services.preprocessing import (
    OUTPUT_COLS,
    DataFramePreprocessingService,
    save_processed_csv,
)


TODAY = date.today().strftime("%Y%m%d")
RAW = ROOT_DIR / "data" / "raw"
PROC = ROOT_DIR / "data" / "processed"
FINAL = ROOT_DIR / "data" / "final"
EXCLUDE_DIRS = {"phishing_url"}
LABEL_NAMES = {0: "phishing", 1: "spam", 2: "legitimate"}
TRAIN_RATIO = 0.80
VAL_RATIO = 0.10
TEST_RATIO = 0.10
RANDOM_STATE = 42


class ProcessedExportsService:
    def __init__(self) -> None:
        self.preprocessing_service = DataFramePreprocessingService()

    def process_df(self, dataframe: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
        result = self.preprocessing_service.process_dataframe(dataframe)
        return result.dataframe, result.dropped_short, result.dropped_duplicate

    def save_csv(self, dataframe: pd.DataFrame, path: Path, label_name: str) -> None:
        save_processed_csv(dataframe, path)
        print(f"  ✅ Saved {path} ({len(dataframe)} rows, {label_name})")

    def load_afi(self) -> pd.DataFrame:
        dataframe = pd.read_csv(
            RAW / "scraping" / "afi_french" / "afi_french_scam_125_20260301.csv"
        )
        return pd.DataFrame(
            {
                "text": dataframe["body"],
                "label": 0,
                "source": "afi_french_forum",
                "language": "fr",
                "archetype": "",
            }
        )

    def load_certfr(self) -> pd.DataFrame:
        dataframe = pd.read_csv(
            RAW / "scraping" / "certfr" / "certfr_phishing_37_20260301.csv"
        )
        return pd.DataFrame(
            {
                "text": dataframe["text"],
                "label": 0,
                "source": "certfr_phishing",
                "language": "fr",
                "archetype": "",
            }
        )

    def load_sap(self, label_filter: str) -> pd.DataFrame:
        data = json.loads((RAW / "scraping" / "sap_labs_fr_emails_18.json").read_text())
        emails = [item for item in data["emails"] if item["label"] == label_filter]
        return pd.DataFrame(
            {
                "text": [
                    f"De: {item['sender']}\nObjet: {item['subject']}\n\n{item['body']}"
                    for item in emails
                ],
                "label": 0,
                "source": "sap_labs_blog",
                "language": "fr",
                "archetype": "",
            }
        )

    def load_kaggle_fr(self, label_filter: str) -> pd.DataFrame:
        dataframe = pd.read_csv(
            RAW / "csv" / "fr" / "kaggle_multilingual_fr_4981_20260301.csv"
        )
        dataframe = dataframe[dataframe["label"] == label_filter].copy()
        dataframe["archetype"] = ""
        return dataframe

    def load_french_spamham(self, label_filter: str) -> pd.DataFrame:
        dataframe = pd.read_csv(RAW / "csv" / "fr" / "french_spamham_1000_20260301.csv")
        dataframe = dataframe[dataframe["label"] == label_filter].copy()
        dataframe["archetype"] = ""
        return dataframe

    def load_phishtank(self) -> pd.DataFrame:
        dataframe = pd.read_csv(RAW / "api" / "phishtank" / "phishing-tank.csv")
        dataframe = dataframe[dataframe["verified"] == "yes"].copy()
        return dataframe.drop_duplicates(subset="url", keep="first").reset_index(
            drop=True
        )

    def restructure_processed_exports(self) -> None:
        print("=" * 60)
        print("SICURRE — Process & Restructure data/processed/")
        print("=" * 60)

        print("\n📁 phishing/fr_phishing/ — Real FR phishing sources")
        afi = self.load_afi()
        certfr = self.load_certfr()
        sap_phish = self.load_sap("phishing")
        fr_phishing = pd.concat([afi, certfr, sap_phish], ignore_index=True)
        print(f"  AFI loaded: {len(afi)} rows")
        print(f"  CERT-FR loaded: {len(certfr)} rows")
        print(f"  SAP phishing loaded: {len(sap_phish)} rows")
        print(f"  Combined: {len(fr_phishing)} rows (pre-processing)")
        fr_phishing, short, dup = self.process_df(fr_phishing)
        print(
            f"  After processing: {len(fr_phishing)} rows (dropped: {short} short, {dup} dup)"
        )
        out = (
            PROC
            / "phishing"
            / "fr_phishing"
            / f"fr_phishing_clean_{len(fr_phishing)}_{TODAY}.csv"
        )
        self.save_csv(fr_phishing, out, "phishing")

        print("\n📁 phishing/adapted/ — Move existing adapted_clean")
        src_adapted = PROC / "adapted" / "adapted_clean_2145_20260301.csv"
        dst_adapted = PROC / "phishing" / "adapted" / "adapted_clean_2145_20260301.csv"
        dst_adapted.parent.mkdir(parents=True, exist_ok=True)
        if src_adapted.exists():
            df_adapted = pd.read_csv(src_adapted)
            df_adapted["label"] = 0
            df_adapted.to_csv(dst_adapted, index=False)
            print(
                f"  ✅ Copied + remapped label→0: {dst_adapted} ({len(df_adapted)} rows)"
            )
        elif dst_adapted.exists():
            print(f"  ⏭️  Already at {dst_adapted}")
        else:
            print(f"  ⚠️  Source not found: {src_adapted}")

        print("\n📁 phishing/synthetic/ — Move existing synthetic_clean")
        src_synth = PROC / "synthetic" / "synthetic_clean_1747_20260301.csv"
        dst_synth = (
            PROC / "phishing" / "synthetic" / "synthetic_clean_1747_20260301.csv"
        )
        dst_synth.parent.mkdir(parents=True, exist_ok=True)
        if src_synth.exists():
            df_synth = pd.read_csv(src_synth)
            df_synth["label"] = 0
            df_synth.to_csv(dst_synth, index=False)
            print(f"  ✅ Copied + remapped label→0: {dst_synth} ({len(df_synth)} rows)")
        elif dst_synth.exists():
            print(f"  ⏭️  Already at {dst_synth}")
        else:
            print(f"  ⚠️  Source not found: {src_synth}")

        print("\n📁 phishing/phishing_url/ — PhishTank verified URLs")
        phishtank = self.load_phishtank()
        print(f"  Loaded: {len(phishtank)} verified unique URLs (from 56,071 raw)")
        out_pt = (
            PROC
            / "phishing"
            / "phishing_url"
            / f"phishtank_urls_clean_{len(phishtank)}_{TODAY}.csv"
        )
        out_pt.parent.mkdir(parents=True, exist_ok=True)
        pt_out = phishtank[["phish_id", "url", "submission_time", "target"]].copy()
        pt_out.to_csv(out_pt, index=False)
        print(f"  ✅ Saved {out_pt} ({len(pt_out)} rows)")

        print("\n📁 spam/ — Real FR spam")
        kaggle_spam = self.load_kaggle_fr("spam")
        kaggle_spam["label"] = 1
        fsh_spam = self.load_french_spamham("spam")
        fsh_spam["label"] = 1
        print(f"  Kaggle FR spam loaded: {len(kaggle_spam)} rows")
        print(f"  French SpamHam spam loaded: {len(fsh_spam)} rows")
        fr_spam = pd.concat([kaggle_spam, fsh_spam], ignore_index=True)
        fr_spam["archetype"] = ""
        print(f"  Combined: {len(fr_spam)} rows (pre-processing)")
        fr_spam, short, dup = self.process_df(fr_spam)
        print(
            f"  After processing: {len(fr_spam)} rows (dropped: {short} short, {dup} dup)"
        )
        out_spam = PROC / "spam" / f"fr_spam_clean_{len(fr_spam)}_{TODAY}.csv"
        self.save_csv(fr_spam, out_spam, "spam")

        print("\n📁 legitimate/fr_legit/ — Real FR legitimate")
        kaggle_ham = self.load_kaggle_fr("ham")
        kaggle_ham["label"] = 2
        fsh_ham = self.load_french_spamham("ham")
        fsh_ham["label"] = 2
        sap_legit = self.load_sap("legitimate")
        sap_legit["label"] = 2
        print(f"  Kaggle FR ham loaded: {len(kaggle_ham)} rows")
        print(f"  French SpamHam ham loaded: {len(fsh_ham)} rows")
        print(f"  SAP legit loaded: {len(sap_legit)} rows")
        fr_legit = pd.concat([kaggle_ham, fsh_ham, sap_legit], ignore_index=True)
        fr_legit["archetype"] = ""
        print(f"  Combined: {len(fr_legit)} rows (pre-processing)")
        fr_legit, short, dup = self.process_df(fr_legit)
        print(
            f"  After processing: {len(fr_legit)} rows (dropped: {short} short, {dup} dup)"
        )
        out_legit = (
            PROC
            / "legitimate"
            / "fr_legit"
            / f"fr_legit_clean_{len(fr_legit)}_{TODAY}.csv"
        )
        self.save_csv(fr_legit, out_legit, "legitimate")

        print("\n📁 legitimate/fr_synthetic/ — Synthetic FR legit (from NB11)")
        existing_legit = pd.read_csv(
            PROC / "legitimate" / "legitimate_clean_7461_20260301.csv"
        )
        fr_synth_legit = existing_legit[
            existing_legit["source"] == "synthetic_fr"
        ].copy()
        fr_synth_legit["label"] = 2
        print(f"  Extracted: {len(fr_synth_legit)} FR synthetic legit rows")
        out_synth_legit = (
            PROC
            / "legitimate"
            / "fr_synthetic"
            / f"fr_synthetic_legit_clean_{len(fr_synth_legit)}_{TODAY}.csv"
        )
        self.save_csv(fr_synth_legit, out_synth_legit, "legitimate")

        print("\n🧹 Cleaning up old flat structure…")
        old_adapted = PROC / "adapted"
        old_synthetic = PROC / "synthetic"
        old_legit_csv = PROC / "legitimate" / "legitimate_clean_7461_20260301.csv"

        for path in [
            old_adapted / ".gitkeep",
            old_adapted / "adapted_clean_2145_20260301.csv",
            old_synthetic / ".gitkeep",
            old_synthetic / "synthetic_clean_1747_20260301.csv",
        ]:
            if path.exists():
                path.unlink()
                print(f"  Removed {path}")

        for directory in [old_adapted, old_synthetic]:
            if directory.exists() and not any(directory.iterdir()):
                directory.rmdir()
                print(f"  Removed empty dir {directory}")

        if old_legit_csv.exists():
            old_legit_csv.unlink()
            print(f"  Removed {old_legit_csv}")

        old_legit_gitkeep = PROC / "legitimate" / ".gitkeep"
        if old_legit_gitkeep.exists():
            old_legit_gitkeep.unlink()
            print(f"  Removed {old_legit_gitkeep}")

        total_phishing = len(fr_phishing) + 2145 + 1747
        total_spam = len(fr_spam)
        total_legit = len(fr_legit) + len(fr_synth_legit)
        print("\n" + "=" * 60)
        print("FINAL STRUCTURE")
        print("=" * 60)
        print(
            f"""
data/processed/
├── phishing/
│   ├── fr_phishing/     {len(fr_phishing):>5} rows  (AFI + CERT-FR + SAP phishing)
│   ├── adapted/         2,145 rows  (existing adapted_clean)
│   ├── synthetic/       1,747 rows  (existing synthetic_clean)
│   └── phishing_url/   {len(pt_out):>5} rows  (PhishTank verified URLs)
├── spam/
│   └── fr_spam_clean   {len(fr_spam):>5} rows  (Kaggle FR + French SpamHam spam)
└── legitimate/
    ├── fr_legit/        {len(fr_legit):>5} rows  (Kaggle FR + French SpamHam + SAP legit)
    └── fr_synthetic/      {len(fr_synth_legit):>3} rows  (NB11 synthetic legit)

TOTALS (French data only):
  Phishing (label=0): {total_phishing:,} rows
  Spam (label=1):     {total_spam:,} rows
  Legitimate (label=2): {total_legit:,} rows
  Grand total:        {total_phishing + total_spam + total_legit:,} rows
  + PhishTank URLs:   {len(pt_out):,} (metadata, not email bodies)
"""
        )

    def collect_csvs(self) -> pd.DataFrame:
        dataframes: list[pd.DataFrame] = []
        for csv_path in sorted(PROC.rglob("*.csv")):
            if any(part in EXCLUDE_DIRS for part in csv_path.parts):
                print(f"  ⏭️  Skipping (URL metadata): {csv_path.relative_to(PROC)}")
                continue
            dataframe = pd.read_csv(csv_path)
            for column in OUTPUT_COLS:
                if column not in dataframe.columns:
                    dataframe[column] = ""
            is_synthetic = (
                "synth" in csv_path.stem.lower() or "synthetic" in csv_path.stem.lower()
            )
            dataframe["is_synthetic"] = is_synthetic
            print(
                f"  📄 {csv_path.relative_to(PROC)}: {len(dataframe)} rows "
                f"({'synthetic' if is_synthetic else 'real'})"
            )
            dataframes.append(dataframe[OUTPUT_COLS + ["is_synthetic"]])

        if not dataframes:
            raise RuntimeError("No CSV files found in data/processed/")
        return pd.concat(dataframes, ignore_index=True)

    def global_dedup(self, dataframe: pd.DataFrame) -> pd.DataFrame:
        before = len(dataframe)
        deduped_df = dataframe.copy()
        deduped_df["_hash"] = (
            deduped_df["text"]
            .astype(str)
            .str[:300]
            .apply(
                lambda text: hashlib.sha256(
                    text.encode("utf-8", errors="ignore")
                ).hexdigest()
            )
        )
        deduped_df = (
            deduped_df.drop_duplicates(subset="_hash", keep="first")
            .drop(columns="_hash")
            .reset_index(drop=True)
        )
        dropped = before - len(deduped_df)
        if dropped:
            print(f"  🔄 Global dedup removed {dropped} cross-source duplicates")
        return deduped_df

    def stratified_split(
        self,
        dataframe: pd.DataFrame,
        downsample_to: int | None = None,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        working_df = dataframe
        if downsample_to and downsample_to > 0:
            print(f"\n  📉 Downsampling each class to max {downsample_to}...")
            capped_frames: list[pd.DataFrame] = []
            for label in sorted(working_df["label"].unique()):
                class_df = working_df[working_df["label"] == label]
                if len(class_df) > downsample_to:
                    real = class_df[~class_df["is_synthetic"]]
                    synth = class_df[class_df["is_synthetic"]]
                    real_target = min(
                        len(real), int(downsample_to * len(real) / len(class_df))
                    )
                    synth_target = downsample_to - real_target
                    if real_target < len(real):
                        real = real.sample(n=real_target, random_state=RANDOM_STATE)
                    if synth_target < len(synth):
                        synth = synth.sample(n=synth_target, random_state=RANDOM_STATE)
                    class_df = pd.concat([real, synth], ignore_index=True)
                    print(
                        f"    {LABEL_NAMES.get(label, label)}: capped to {len(class_df)} "
                        f"({len(real)} real + {len(synth)} synth)"
                    )
                capped_frames.append(class_df)
            working_df = pd.concat(capped_frames, ignore_index=True)

        working_df = working_df.copy()
        working_df["_strat"] = (
            working_df["label"].astype(str)
            + "_"
            + working_df["is_synthetic"].astype(str)
        )

        train_parts: list[pd.DataFrame] = []
        val_parts: list[pd.DataFrame] = []
        test_parts: list[pd.DataFrame] = []
        for _strat_key, group in working_df.groupby("_strat"):
            group_shuffled = group.sample(
                frac=1.0, random_state=RANDOM_STATE
            ).reset_index(drop=True)
            count = len(group_shuffled)
            n_test = max(1, round(count * TEST_RATIO))
            n_val = max(1, round(count * VAL_RATIO))
            n_train = count - n_val - n_test
            train_parts.append(group_shuffled.iloc[:n_train])
            val_parts.append(group_shuffled.iloc[n_train : n_train + n_val])
            test_parts.append(group_shuffled.iloc[n_train + n_val :])

        train_df = pd.concat(train_parts, ignore_index=True)
        val_df = pd.concat(val_parts, ignore_index=True)
        test_df = pd.concat(test_parts, ignore_index=True)
        for split_df in [train_df, val_df, test_df]:
            split_df.drop(columns=["_strat", "is_synthetic"], inplace=True)

        return (
            train_df.sample(frac=1.0, random_state=RANDOM_STATE).reset_index(drop=True),
            val_df.sample(frac=1.0, random_state=RANDOM_STATE).reset_index(drop=True),
            test_df.sample(frac=1.0, random_state=RANDOM_STATE).reset_index(drop=True),
        )

    def save_split(self, dataframe: pd.DataFrame, split_name: str) -> Path:
        out_dir = FINAL / split_name
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"sicurre_{split_name}.csv"
        dataframe[OUTPUT_COLS].to_csv(out_path, index=False)
        return out_path

    def print_split_stats(self, dataframe: pd.DataFrame, name: str) -> None:
        print(f"\n  📊 {name} split ({len(dataframe)} rows):")
        for label in sorted(dataframe["label"].unique()):
            count = len(dataframe[dataframe["label"] == label])
            label_name = LABEL_NAMES.get(label, f"label={label}")
            print(
                f"     {label_name:<12s} {count:>6d}  ({count / len(dataframe) * 100:.1f}%)"
            )

    def build_dataset_splits(self, downsample_to: int = 0) -> None:
        print("=" * 60)
        print("  SICURRE — Data Merge & Split")
        print(f"  Date: {TODAY}")
        print(f"  Split ratio: {TRAIN_RATIO:.0%} / {VAL_RATIO:.0%} / {TEST_RATIO:.0%}")
        print("=" * 60)

        print("\n📁 Collecting processed CSVs...")
        dataframe = self.collect_csvs()
        print(f"\n  Total merged: {len(dataframe)} rows")

        print("\n🔄 Running global deduplication...")
        dataframe = self.global_dedup(dataframe)
        print(f"  After dedup: {len(dataframe)} rows")

        print("\n📈 Class distribution (before split):")
        for label in sorted(dataframe["label"].unique()):
            count = len(dataframe[dataframe["label"] == label])
            real = len(
                dataframe[(dataframe["label"] == label) & (~dataframe["is_synthetic"])]
            )
            synth = count - real
            label_name = LABEL_NAMES.get(label, f"label={label}")
            print(
                f"  {label_name:<12s} {count:>6d}  (real={real}, synth={synth}, real%={real/count*100:.0f}%)"
            )

        print("\n✂️  Performing stratified split...")
        downsample = downsample_to if downsample_to > 0 else None
        train_df, val_df, test_df = self.stratified_split(
            dataframe, downsample_to=downsample
        )

        print("\n💾 Saving splits...")
        for split_name, split_df in [
            ("train", train_df),
            ("val", val_df),
            ("test", test_df),
        ]:
            path = self.save_split(split_df, split_name)
            self.print_split_stats(split_df, split_name)
            print(f"     → {path.relative_to(ROOT_DIR)}")

        total = len(train_df) + len(val_df) + len(test_df)
        print(f"\n{'='*60}")
        print(f"  TOTAL: {total} rows")
        print(f"  Train: {len(train_df)} ({len(train_df)/total*100:.1f}%)")
        print(f"  Val:   {len(val_df)} ({len(val_df)/total*100:.1f}%)")
        print(f"  Test:  {len(test_df)} ({len(test_df)/total*100:.1f}%)")
        print(f"{'='*60}")
        print("  Done! 🎉")
