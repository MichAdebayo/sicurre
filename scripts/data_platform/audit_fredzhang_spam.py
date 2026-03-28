"""
Audit FredZhang7/all-scam-spam dataset for French content.
Downloads via HuggingFace datasets library, checks language distribution.
"""

from datasets import load_dataset
import pandas as pd

print("Loading FredZhang7/all-scam-spam...")
ds = load_dataset("FredZhang7/all-scam-spam", split="train")
df: pd.DataFrame = ds.to_pandas()  # type: ignore[assignment]

print(f"Total rows: {len(df)}")
print(f"Columns: {list(df.columns)}")
print(f"\nis_spam distribution:\n{df['is_spam'].value_counts()}")
print(f"\nSample row:\n{df.iloc[0].to_dict()}")

# Check if there's a language column
if "language" in df.columns or "lang" in df.columns:
    lang_col = "language" if "language" in df.columns else "lang"
    print(f"\nLanguage distribution (top 15):")
    print(df[lang_col].value_counts().head(15))
    fr = df[df[lang_col].str.contains("fr", case=False, na=False)]
    print(f"\nFrench rows: {len(fr)}")
    if len(fr) > 0:
        print(f"  spam: {(fr['is_spam']==1).sum()}")
        print(f"  ham:  {(fr['is_spam']==0).sum()}")
        fr_lens = fr["text"].str.len()
        print(
            f"  text length: min={fr_lens.min()}, max={fr_lens.max()}, mean={fr_lens.mean():.0f}, median={fr_lens.median():.0f}"
        )
        print(f"\n--- 5 French spam samples ---")
        for _, row in (
            fr[fr["is_spam"] == 1]
            .sample(min(5, len(fr[fr["is_spam"] == 1])), random_state=42)
            .iterrows()
        ):
            print(f"  [{len(row['text'])} chars] {row['text'][:200]}")
            print()
else:
    # No language column — try language detection on a sample
    print("\nNo language column found. Attempting langdetect on sample...")
    try:
        from langdetect import detect, LangDetectException

        sample = df.sample(min(2000, len(df)), random_state=42)
        langs = []
        for text in sample["text"]:
            try:
                langs.append(detect(str(text)[:500]))
            except LangDetectException:
                langs.append("unknown")
        lang_series = pd.Series(langs)
        print(f"Language distribution (sample of {len(sample)}):")
        print(lang_series.value_counts().head(15))

        # Now detect all French
        print("\nDetecting French in full dataset (this may take a minute)...")
        fr_flags = []
        for text in df["text"]:
            try:
                fr_flags.append(detect(str(text)[:500]) == "fr")
            except LangDetectException:
                fr_flags.append(False)
        df["is_french"] = fr_flags
        fr = df[df["is_french"]]
        print(f"\nFrench rows: {len(fr)}")
        if len(fr) > 0:
            print(f"  spam: {(fr['is_spam']==1).sum()}")
            print(f"  ham:  {(fr['is_spam']==0).sum()}")
            fr_lens = fr["text"].str.len()
            print(
                f"  text length: min={fr_lens.min()}, max={fr_lens.max()}, mean={fr_lens.mean():.0f}, median={fr_lens.median():.0f}"
            )
            print(f"\n--- 5 French spam samples ---")
            for _, row in (
                fr[fr["is_spam"] == 1]
                .sample(min(5, len(fr[fr["is_spam"] == 1])), random_state=42)
                .iterrows()
            ):
                print(f"  [{len(row['text'])} chars] {row['text'][:250]}")
                print()
            print(f"\n--- 5 French ham samples ---")
            for _, row in (
                fr[fr["is_spam"] == 0]
                .sample(min(5, len(fr[fr["is_spam"] == 0])), random_state=42)
                .iterrows()
            ):
                print(f"  [{len(row['text'])} chars] {row['text'][:250]}")
                print()
    except ImportError:
        print("langdetect not installed. Install with: pip install langdetect")
        # Fallback: just check for French words
        fr_keywords = [
            "bonjour",
            "merci",
            "cordialement",
            "madame",
            "monsieur",
            "veuillez",
            "cher client",
            "votre compte",
        ]
        fr_mask = df["text"].str.lower().str.contains("|".join(fr_keywords), na=False)
        print(f"Rows containing French keywords: {fr_mask.sum()}")
        if fr_mask.sum() > 0:
            sample_fr = df[fr_mask].head(5)
            for _, row in sample_fr.iterrows():
                print(f"  [{len(row['text'])} chars] {row['text'][:200]}")
                print()
