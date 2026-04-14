"""
Script to improve the 1.3.0 dataset quality by:
  1. Translating English/weak items to French.
  2. Wrapping short review fragments into fully-formed emails.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from deep_translator import GoogleTranslator

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "local" / "sicurre.db"

FRENCH_MARKERS = ("vous", "votre", "veuillez", "cordialement", "madame", "monsieur",
                  "bonjour", "é", "è", "ê", "ë", "à", "ù", "ç", "ô")
ENGLISH_MARKERS = ("the", "you", "your", "please", "click", "dear",
                   "sincerely", "regard", "account", "password")

LEGIT_TEMPLATES = [
    "Objet : Mon avis sur votre service\n\nBonjour,\n\nJe voulais partager mon retour avec vous : {text}\n\nCordialement,\nUn client",
    "Objet : Retour d'expérience\n\nBonjour l'équipe,\n\nVoici ce que je pense : {text}\n\nBonne journée.",
    "Objet : Mon retour de satisfaction\n\nBonjour,\n\nJe vous fais part de mon évaluation suite à ma commande : {text}\n\nMerci,\nBien à vous.",
]

SPAM_TEMPLATES = [
    "Objet : {text}\n\nNe manquez pas cette opportunité incroyable ! Cliquez ici pour en savoir plus.\n\nÀ très vite !\n\nSi vous ne souhaitez plus recevoir d'emails, cliquez sur se désabonner.",
    "Objet : A ne pas manquer : {text}\n\nBonjour,\n\nProfitez de notre offre exclusive aujourd'hui.\n\nCordialement.",
]

def detect_quality(text: str) -> str:
    lowered = text.lower()
    fr_count = sum(1 for m in FRENCH_MARKERS if m in lowered)
    en_count = sum(1 for m in ENGLISH_MARKERS if m in lowered)
    if fr_count == 0 and en_count >= 2: return "english_only"
    elif fr_count <= 1 and en_count >= 3: return "mostly_english"
    elif len(text) < 50: return "too_short"
    elif fr_count >= 3: return "good_french"
    elif fr_count >= 1: return "weak_french"
    else: return "ambiguous"

def process_item(item: tuple[str, str, str]) -> tuple[str, str, str, str | None, int]:
    # item: id, text, label
    msg_id, text, label = item
    quality = detect_quality(text)
    
    if quality == "good_french":
        return msg_id, text, quality, None, 0

    new_text = text
    action = None

    # Step 1: Translate if mostly English
    if quality in ("english_only", "mostly_english"):
        try:
            translator = GoogleTranslator(source='auto', target='fr')
            new_text = translator.translate(text)
            action = "translated"
        except Exception as e:
            print(f"Translation failed for {msg_id}: {e}")
            return msg_id, text, quality, "failed", 0

    # Step 2: Wrap if too short / ambiguous / lacked structure
    import random
    if detect_quality(new_text) in ("too_short", "ambiguous", "weak_french"):
        if "Objet :" not in new_text and label == "legitimate":
            new_text = random.choice(LEGIT_TEMPLATES).format(text=new_text.strip())
            action = "translated_and_wrapped" if action else "wrapped"
        elif "Objet :" not in new_text and label == "spam":
            # For spam, wrap it if it's super short
            if len(new_text) < 60:
                new_text = random.choice(SPAM_TEMPLATES).format(text=new_text.strip().replace("Objet :", "").strip())
                action = "translated_and_wrapped" if action else "wrapped"

    # Re-hash & get new len
    new_hash = hashlib.sha256(new_text.encode("utf-8")).hexdigest()
    new_len = len(new_text)

    return msg_id, new_text, quality, action, new_len


async def main():
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    print("Fetching 1.3.0 records...")
    cur.execute("""
        SELECT nm.id, nm.normalized_text, nm.current_label
        FROM data_normalized_message nm
        JOIN data_processing_run pr ON nm.processing_run_id = pr.id
        WHERE pr.pipeline_version = '1.3.0'
    """)
    rows = cur.fetchall()
    
    items_to_process = []
    for r in rows:
        q = detect_quality(r[1])
        if q != "good_french":
            items_to_process.append(r)
            
    print(f"Found {len(items_to_process)} records needing improvement.")
    
    results = []
    actions = {"translated": 0, "wrapped": 0, "translated_and_wrapped": 0, "failed": 0, "none": 0}
    
    # Process concurrent translation
    with ThreadPoolExecutor(max_workers=10) as executor:
        loop = asyncio.get_running_loop()
        tasks = [
            loop.run_in_executor(executor, process_item, item)
            for item in items_to_process
        ]
        
        chunk_size = 500
        completed = 0
        for i in range(0, len(tasks), chunk_size):
            chunk = tasks[i:i+chunk_size]
            chunk_results = await asyncio.gather(*chunk)
            results.extend(chunk_results)
            completed += len(chunk)
            print(f"  Processed {completed}/{len(items_to_process)}...")

    # Update DB
    print("\nUpdating DB...")
    update_batch = []
    for res in results:
        msg_id, new_text, quality, action, new_len = res
        if action:
            actions[action] += 1
            new_hash = hashlib.sha256(new_text.encode("utf-8")).hexdigest()
            update_batch.append((new_text, new_hash, new_len, msg_id))
        else:
            actions["none"] += 1

    cur.executemany("""
        UPDATE data_normalized_message 
        SET normalized_text = ?, 
            text_sha256 = ?, 
            text_length = ?, 
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, update_batch)
    
    conn.commit()
    conn.close()

    print(f"\nImproved {len(update_batch)} records.")
    for k, v in actions.items():
        if v > 0:
            print(f"  {k}: {v}")

if __name__ == "__main__":
    asyncio.run(main())
