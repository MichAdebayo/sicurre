# /// script
# requires-python = ">=3.12,<3.14"
# dependencies = [
#   "torch",
#   "transformers",
#   "huggingface_hub",
#   "python-dotenv",
#   "sentencepiece",
# ]
# ///
"""Smoke test — local inference for Mikolinton/sicurre-phishing-fr.

The hf-inference serverless provider only serves its own curated catalog of
popular models — custom fine-tunes are not supported by it.  This script
downloads the model weights from the HF Hub using HF_TOKEN and runs inference
locally via transformers.pipeline (Python 3.12 required; torch not yet released
for Python 3.14).

Usage:
    uv run --python 3.12 tests/e2e/app/smoke_hf_inference.py

Exit 0  → all probes classified without error.
Exit 1  → at least one probe failed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# ── Load token ────────────────────────────────────────────────────────────────
load_dotenv(Path(__file__).parents[3] / ".env")

HF_TOKEN = os.getenv("HF_TOKEN")
if not HF_TOKEN:
    print("FAIL  HF_TOKEN not set in .env", file=sys.stderr)
    sys.exit(1)

MODEL_ID = "Mikolinton/sicurre-phishing-fr"

# ── Test cases ────────────────────────────────────────────────────────────────
# (text, expected_top_label)  — hint only, not a hard assertion
PROBES: list[tuple[str, str]] = [
    (
        "Urgent : Votre compte bancaire a été suspendu. "
        "Cliquez ici pour le réactiver immédiatement : http://secure-banque-fr.xyz/login",
        "phishing",
    ),
    (
        "FÉLICITATIONS ! Vous avez gagné un iPhone 15. "
        "Répondez maintenant pour réclamer votre prix. Offre valable 24h.",
        "spam",
    ),
    (
        "Bonjour, je vous envoie le compte-rendu de la réunion du 20 mai. "
        "Merci de me confirmer la date de la prochaine session.",
        "legitimate",
    ),
]

# ── Load model locally (token auth for private / newly public model) ──────────
from transformers import pipeline  # noqa: E402 — after dotenv

print(f"\nModèle : {MODEL_ID}")
print("Chargement du modèle (premier appel = téléchargement du cache HF)…")

clf = pipeline(
    "text-classification",
    model=MODEL_ID,
    token=HF_TOKEN,
    top_k=None,  # return scores for all labels
)

# ── Run probes ────────────────────────────────────────────────────────────────
all_passed = True

print(f"\n{'─' * 60}")

for i, (text, hint) in enumerate(PROBES, 1):
    print(f"\nProbe {i}/{len(PROBES)}  (expected ~ {hint})")
    print(f"  Input : {text[:80]}{'…' if len(text) > 80 else ''}")

    try:
        raw = clf(text)
    except Exception as exc:
        print(f"  FAIL  {type(exc).__name__}: {exc}")
        all_passed = False
        continue

    # pipeline returns [[{label, score}, ...]] when top_k=None
    scores: list[dict] = raw[0] if isinstance(raw[0], list) else raw
    scores_sorted = sorted(scores, key=lambda x: x["score"], reverse=True)

    top = scores_sorted[0]
    match_hint = "✓" if top["label"] == hint else f"≠ hint({hint})"
    print(f"  PASS  top={top['label']}  score={top['score']:.4f}  {match_hint}")
    for entry in scores_sorted[1:]:
        print(f"        {entry['label']:<12} {entry['score']:.4f}")

print(f"\n{'─' * 60}")
if all_passed:
    print("All probes passed.\n")
    sys.exit(0)
else:
    print("One or more probes failed. See output above.\n")
    sys.exit(1)
