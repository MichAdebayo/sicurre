#!/usr/bin/env python3
"""
Resilient AFI French scam email scraper via Wayback Machine.

Features:
- Exponential backoff on rate limiting (Connection refused / 429)
- Progress persistence (resume from where we left off)
- CSV flushing after each write
- Configurable delay between requests
- Also searches "unknown" language threads for French content
"""
import csv
import json
import re
import sys
import time
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------
OUTPUT_DIR = Path("data/raw/scraping/afi_french")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

CSV_PATH = OUTPUT_DIR / "afi_french_scam_emails_v2.csv"
PROGRESS_PATH = OUTPUT_DIR / "bulk_progress.json"
INVENTORY_PATH = OUTPUT_DIR / "all_archived_threads_inventory.json"

TIMEOUT = httpx.Timeout(60.0, connect=30.0)
BASE_DELAY = 3.0  # seconds between requests (polite)
BACKOFF_BASE = 30.0  # seconds to wait after rate limit
MAX_BACKOFF = 300.0  # max backoff (5 minutes)
MAX_CONSECUTIVE_ERRORS = 5  # pause after this many errors in a row


# ------------------------------------------------------------------
# Language classification
# ------------------------------------------------------------------
def classify_slug_language(slug: str) -> str:
    """Classify likely language from URL slug."""
    s = slug.lower()

    fr_strong = [
        "mme-",
        "mlle-",
        "madame-",
        "monsieur-",
        "-francais",
        "-francaise",
        "nationalite-",
        "-belge",
        "-ivoirienne",
        "-senegalais",
        "loterie-",
        "heritage-",
        "banque-",
        "gouvernement-",
        "republique-",
        "cote-divoire",
        "-afrique",
        "-africain",
        "avocat-",
        "notaire-",
        "consul-",
        "ambassad-",
        "veuve-",
        "orphelin-",
        "malade-",
        "mourant-",
        "deces-",
        "donation-",
        "legs-",
        "testament-",
    ]
    fr_moderate = [
        "jean-",
        "pierre-",
        "marie-",
        "jacques-",
        "claude-",
        "philippe-",
        "henri-",
        "louis-",
        "francois-",
        "bernard-",
        "andre-",
        "alain-",
        "paul-",
        "rene-",
        "thierry-",
        "-burkina",
        "-cameroun",
        "-congo",
        "-gabon",
        "-mali",
        "-togo",
        "-benin",
        "-guinee",
    ]
    en_strong = [
        "-nigerian",
        "-ghana",
        "-scammer",
        "-lottery",
        "dear-sir",
        "attention-",
        "the-",
        "from-the-",
    ]

    fr_s = sum(1 for p in fr_strong if p in s)
    fr_m = sum(1 for p in fr_moderate if p in s)
    en_s = sum(1 for p in en_strong if p in s)

    score = fr_s * 3 + fr_m - en_s * 2
    if score >= 3:
        return "fr_likely"
    elif score >= 1:
        return "fr_possible"
    elif en_s >= 1:
        return "en_likely"
    return "unknown"


def detect_french(text: str) -> bool:
    """Detect if text content is likely French."""
    fr_words = [
        "bonjour",
        "monsieur",
        "madame",
        "je suis",
        "nous avons",
        "votre",
        "cette",
        "pour vous",
        "s'il vous",
        "merci",
        "cher ",
        "chère",
        "urgent",
        "confidentiel",
        "héritage",
        "décédé",
        "banque",
        "million",
        "euros",
        "compte",
        "transfert",
        "bénéficiaire",
        "veuillez",
        "contactez",
        "loterie",
        "félicitations",
        "gagnant",
        "notification",
        "gouvernement",
        "république",
        "côte d'ivoire",
        "afrique",
        "je soussigné",
        "cher monsieur",
        "chère madame",
        "ci-joint",
        "prière de",
        "dans l'attente",
        "cordialement",
        "sincères salutations",
        "j'ai l'honneur",
        "permettez-moi",
        "suite à",
        "je me permets",
        "objet :",
        "de la part de",
        "très cher",
        "mon frère",
        "ma soeur",
        "que dieu",
    ]
    text_lower = text.lower()
    return sum(1 for w in fr_words if w in text_lower) >= 2


# ------------------------------------------------------------------
# Fetch + extract
# ------------------------------------------------------------------
def fetch_thread(ts: str, orig: str, retries: int = 3) -> str | None:
    """Fetch a thread page with retry logic."""
    wb_url = f"https://web.archive.org/web/{ts}/{orig}"

    for attempt in range(retries):
        try:
            resp = httpx.get(wb_url, timeout=TIMEOUT, follow_redirects=True)
            if resp.status_code == 200 and len(resp.text) > 3000:
                return resp.text
            elif resp.status_code == 429:
                wait = BACKOFF_BASE * (2**attempt)
                print(f"\n  429 rate limited, waiting {wait:.0f}s...")
                time.sleep(min(wait, MAX_BACKOFF))
                continue
            return None
        except (httpx.ConnectError, ConnectionRefusedError):
            wait = BACKOFF_BASE * (2**attempt)
            print(
                f"\n  Connection refused (attempt {attempt+1}/{retries}), waiting {wait:.0f}s..."
            )
            time.sleep(min(wait, MAX_BACKOFF))
        except httpx.ReadTimeout:
            print(f"\n  Timeout (attempt {attempt+1}/{retries})")
            time.sleep(BASE_DELAY)
        except Exception as e:
            print(f"\n  Error: {e}")
            return None

    return None


def extract_content(html: str) -> tuple[str, list[str]]:
    """Extract title and message texts from a thread page."""
    soup = BeautifulSoup(html, "html.parser")

    title_el = soup.select_one(
        "h1.p-title-value, h1 .titleBar, .titleBar h1, .p-title-value"
    )
    title = title_el.get_text(strip=True) if title_el else ""
    if not title:
        title_el = soup.select_one("title")
        title = title_el.get_text(strip=True) if title_el else ""
    title = re.sub(r"\s*\|\s*antifraudintl\.org\s*$", "", title)

    messages = []
    for sel in [
        ".bbWrapper",
        "blockquote.messageText",
        ".messageContent .messageText",
        ".message-body .bbWrapper",
        "article.message-body .bbWrapper",
        ".messageContent",
    ]:
        elements = soup.select(sel)
        if elements:
            for el in elements:
                text = el.get_text(separator="\n", strip=True)
                if len(text) >= 50:
                    messages.append(text)
            break

    return title, messages


# ------------------------------------------------------------------
# Progress management
# ------------------------------------------------------------------
def load_progress() -> dict:
    if PROGRESS_PATH.exists():
        return json.loads(PROGRESS_PATH.read_text())
    return {
        "completed": [],
        "failed": [],
        "stats": {"fetched": 0, "messages": 0, "french": 0, "errors": 0},
    }


def save_progress(progress: dict):
    PROGRESS_PATH.write_text(json.dumps(progress, indent=2, ensure_ascii=False))


def load_inventory() -> list[dict]:
    """Load or fetch the thread inventory."""
    if INVENTORY_PATH.exists():
        data = json.loads(INVENTORY_PATH.read_text())
        if len(data) > 100:
            print(f"Loaded inventory: {len(data)} threads")
            return data

    print("Fetching thread inventory from CDX...")
    cdx_url = (
        "https://web.archive.org/cdx/search/cdx"
        "?url=antifraudintl.org/threads/*"
        "&output=text"
        "&fl=timestamp,original,statuscode"
        "&filter=statuscode:200"
        "&collapse=urlkey"
        "&limit=10000"
    )
    resp = httpx.get(cdx_url, timeout=httpx.Timeout(120.0), follow_redirects=True)
    lines = [l.strip() for l in resp.text.strip().split("\n") if l.strip()]

    threads = []
    seen = set()
    for line in lines:
        parts = line.split(" ")
        if len(parts) < 3:
            continue
        ts, orig = parts[0], parts[1]
        m = re.search(r"/threads/([^/?#]+\.(\d+))", orig)
        if not m:
            continue
        if "/reply" in orig or "/unread" in orig or "#" in orig:
            continue

        slug = m.group(1).rstrip("/")
        tid = m.group(2)
        if tid in seen:
            continue
        seen.add(tid)

        lang = classify_slug_language(slug)
        threads.append(
            {
                "timestamp": ts,
                "original": orig,
                "slug": slug,
                "thread_id": tid,
                "slug_lang": lang,
            }
        )

    # Save inventory
    INVENTORY_PATH.write_text(json.dumps(threads, indent=2, ensure_ascii=False))
    print(f"Saved inventory: {len(threads)} unique threads")
    return threads


# ------------------------------------------------------------------
# Main scraping loop
# ------------------------------------------------------------------
def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "french"  # french | all | stats

    inventory = load_inventory()
    progress = load_progress()

    if mode == "stats":
        # Just show stats
        langs = {}
        for t in inventory:
            lang = t["slug_lang"]
            langs[lang] = langs.get(lang, 0) + 1
        print(f"\nInventory: {len(inventory)} threads")
        for lang, count in sorted(langs.items(), key=lambda x: -x[1]):
            print(f"  {lang}: {count}")
        print(f"\nProgress: {json.dumps(progress['stats'], indent=2)}")
        print(f"Completed: {len(progress['completed'])}")
        print(f"Failed: {len(progress['failed'])}")
        return

    # Select candidates
    if mode == "french":
        candidates = [
            t for t in inventory if t["slug_lang"] in ("fr_likely", "fr_possible")
        ]
    elif mode == "all":
        # Include unknowns too
        candidates = [t for t in inventory if t["slug_lang"] != "en_likely"]
    else:
        candidates = inventory

    # Filter out already completed/failed
    done_ids = set(progress["completed"]) | set(progress["failed"])
    pending = [t for t in candidates if t["thread_id"] not in done_ids]

    print(f"\nMode: {mode}")
    print(f"Total candidates: {len(candidates)}")
    print(f"Already done: {len(done_ids)}")
    print(f"Pending: {len(pending)}")

    if not pending:
        print("Nothing to do!")
        return

    # Open CSV for append
    csv_exists = CSV_PATH.exists() and CSV_PATH.stat().st_size > 0
    csvfile = open(CSV_PATH, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(
        csvfile,
        fieldnames=[
            "thread_id",
            "title",
            "body",
            "body_length",
            "is_french",
            "slug_lang",
            "slug",
            "wayback_url",
        ],
    )
    if not csv_exists:
        writer.writeheader()
        csvfile.flush()

    consecutive_errors = 0

    try:
        for i, t in enumerate(pending):
            tid = t["thread_id"]
            slug = t["slug"]

            print(f"\r[{i+1}/{len(pending)}] {slug[:55]:<55s}", end="", flush=True)

            html = fetch_thread(t["timestamp"], t["original"])

            if html is None:
                consecutive_errors += 1
                progress["failed"].append(tid)
                progress["stats"]["errors"] += 1

                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    wait = min(
                        BACKOFF_BASE
                        * (2 ** (consecutive_errors - MAX_CONSECUTIVE_ERRORS)),
                        MAX_BACKOFF,
                    )
                    print(
                        f"\n  {consecutive_errors} consecutive errors, cooling down {wait:.0f}s..."
                    )
                    time.sleep(wait)

                save_progress(progress)
                time.sleep(BASE_DELAY)
                continue

            # Success — reset error counter
            consecutive_errors = 0
            progress["stats"]["fetched"] += 1

            title, messages = extract_content(html)

            if messages:
                for msg in messages:
                    is_fr = detect_french(msg)
                    writer.writerow(
                        {
                            "thread_id": tid,
                            "title": title,
                            "body": msg,
                            "body_length": len(msg),
                            "is_french": is_fr,
                            "slug_lang": t["slug_lang"],
                            "slug": slug,
                            "wayback_url": f"https://web.archive.org/web/{t['timestamp']}/{t['original']}",
                        }
                    )
                    progress["stats"]["messages"] += 1
                    if is_fr:
                        progress["stats"]["french"] += 1
                csvfile.flush()

            progress["completed"].append(tid)
            save_progress(progress)

            # Progress report every 20
            if (i + 1) % 20 == 0:
                s = progress["stats"]
                print(
                    f"\n  === {s['fetched']} fetched, {s['messages']} msgs, {s['french']} FR, {s['errors']} err ==="
                )

            time.sleep(BASE_DELAY)

    except KeyboardInterrupt:
        print("\n\nInterrupted! Progress saved.")
    finally:
        csvfile.close()
        save_progress(progress)

    # Final report
    s = progress["stats"]
    print(f"\n\n{'='*60}")
    print(f"RESULTS")
    print(f"{'='*60}")
    print(f"Fetched: {s['fetched']}")
    print(f"Messages: {s['messages']}")
    print(f"French: {s['french']}")
    print(f"Errors: {s['errors']}")
    print(f"CSV: {CSV_PATH}")


if __name__ == "__main__":
    main()
