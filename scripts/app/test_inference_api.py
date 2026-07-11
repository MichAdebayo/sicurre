# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "httpx",
#   "python-dotenv",
# ]
# ///
"""Smoke test — Sicurre inference API (http://localhost:8000).

Endpoint reference
──────────────────
  GET  /v1/health   — no auth; server liveness probe
  GET  /v1/ready    — no auth; ONNX model loaded? (fails until model.onnx lands in HF Hub)
  POST /v1/classify — Bearer INFERENCE_API_KEY; rules + blocklist + optional ONNX + optional LLM

Classify request body
─────────────────────
  {"text": "<message or URL>", "use_llm": false}   ← use_llm=false: rules+blocklist+ONNX only (instant)
  {"text": "<message or URL>", "use_llm": true}    ← use_llm=true:  adds LLM stage

Classify response body
──────────────────────
  {
    "verdict": "phishing",          // top-level decision
    "is_phishing": true,
    "composite_score": 0.73,
    "stage_scores":  {"rules": 0.8, "blocklist": 1.0, "onnx": 0.0, "llm": 0.0},
    "stage_labels":  {"rules": "phishing", "blocklist": "phishing", "onnx": "unknown", "llm": "unknown"},
    "explanation": "...",
    "llm_provider": ""
  }

  onnx stage shows 0.0 / "unknown" until model.onnx is deployed on HF Hub.

Usage
─────
  uv run scripts/app/test_inference_api.py

Exit codes
──────────
  0  → health ✓, classify ✓ (ready may still fail until model lands — that is expected)
  1  → health or classify failed
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[2] / ".env", override=True)

BASE_URL = (
    os.getenv("SICURRE_INFERENCE_API_URL")
    or os.getenv("INFERENCE_API_URL")
    or "http://localhost:8000/v1/classify"
).rsplit("/classify", 1)[0]
API_KEY = os.getenv("INFERENCE_API_KEY") or ""
CLASSIFY_URL = f"{BASE_URL}/classify"
HEALTH_URL = f"{BASE_URL}/health"
READY_URL = f"{BASE_URL}/ready"

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

SEP = "─" * 64


def _verdict_icon(v: str) -> str:
    return {"phishing": "🔴", "spam": "🟡", "legitimate": "🟢"}.get(v, "⚪")


def main() -> int:
    print(f"\n{SEP}")
    print(f"  Sicurre Inference API Smoke Test")
    print(f"  Base URL : {BASE_URL}")
    print(f"  Key      : {API_KEY[:8]}…" if API_KEY else "  Key      : (not set)")
    print(SEP)

    failed = False

    # ── 1. Health ─────────────────────────────────────────────────────────────
    print("\n[1/3] GET /v1/health (no auth)")
    try:
        r = httpx.get(HEALTH_URL, timeout=5.0)
        if r.status_code == 200:
            print(f"  ✓  {r.status_code} {r.json()}")
        else:
            print(f"  ✗  {r.status_code} {r.text}", file=sys.stderr)
            failed = True
    except httpx.ConnectError:
        print(f"  ✗  Cannot connect to {HEALTH_URL}", file=sys.stderr)
        print(
            "     Is the inference server running? (cd sicurre-ml && make serve)",
            file=sys.stderr,
        )
        return 1

    # ── 2. Ready ──────────────────────────────────────────────────────────────
    print("\n[2/3] GET /v1/ready (no auth)")
    try:
        r = httpx.get(READY_URL, timeout=5.0)
        if r.status_code == 200:
            print(f"  ✓  {r.status_code} {r.json()}")
        else:
            data = (
                r.json()
                if r.headers.get("content-type", "").startswith("application/json")
                else r.text
            )
            print(f"  ⚠  {r.status_code} {data}")
            print(
                "     (Expected if ONNX model not yet deployed to HF Hub — not a hard failure)"
            )
    except Exception as exc:
        print(f"  ⚠  {exc}  (not a hard failure)", file=sys.stderr)

    # ── 3. Classify probes ────────────────────────────────────────────────────
    if not API_KEY:
        print("\n[3/3] POST /v1/classify — SKIPPED (INFERENCE_API_KEY not set in .env)")
        return 1 if failed else 0

    print(f"\n[3/3] POST /v1/classify  use_llm=false  (3 probes)")
    client = httpx.Client(
        headers={"Authorization": f"Bearer {API_KEY}"},
        timeout=10.0,
    )
    with client:
        for i, (text, expected_hint) in enumerate(PROBES, 1):
            try:
                r = client.post(CLASSIFY_URL, json={"text": text, "use_llm": False})
                if r.status_code == 200:
                    d = r.json()
                    verdict = d.get("verdict", "?")
                    score = d.get("composite_score", 0.0)
                    icon = _verdict_icon(verdict)
                    match_hint = (
                        "✓"
                        if verdict == expected_hint
                        else f"≠ expected {expected_hint}"
                    )
                    print(
                        f"  {icon} probe {i}: verdict={verdict:<10} score={score:.2f}  [{match_hint}]"
                    )
                    print(
                        f"       stages: {d.get('stage_scores', {})} | labels: {d.get('stage_labels', {})}"
                    )
                    if d.get("explanation"):
                        print(f"       explanation: {d['explanation'][:120]}")
                else:
                    data = (
                        r.json()
                        if r.headers.get("content-type", "").startswith(
                            "application/json"
                        )
                        else r.text
                    )
                    detail = (
                        data.get("detail", data) if isinstance(data, dict) else data
                    )
                    print(
                        f"  ✗  probe {i}: {r.status_code} — {detail}", file=sys.stderr
                    )
                    if "INFERENCE_API_KEY not configured" in str(detail):
                        print(
                            "     → The ML inference server needs INFERENCE_API_KEY in its own .env",
                            file=sys.stderr,
                        )
                        print(f"     → Expected value: {API_KEY[:8]}…", file=sys.stderr)
                    failed = True
            except Exception as exc:
                print(f"  ✗  probe {i}: {exc}", file=sys.stderr)
                failed = True

    print(f"\n{SEP}")
    if failed:
        print("  RESULT: FAILED — see errors above")
        return 1
    print("  RESULT: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
