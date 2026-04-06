"""
Common Crawl extraction — asynchronous, high-yield pipeline.

Strategy:
  - Asynchronously query CC Index APIs
  - Asynchronously download WARC chunks using htppx.AsyncClient
  - Push final datasets directly to Cloudflare R2 via boto3
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import boto3
import httpx
import pandas as pd
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from langdetect import detect, LangDetectException
from warcio.archiveiterator import ArchiveIterator


ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Configurable via .env ────────────────────────────────────────────
MAX_RESULTS_PER_QUERY = int(os.getenv("CC_MAX_RESULTS_PER_QUERY", "5000"))
MAX_WARC_DOWNLOADS = int(os.getenv("CC_MAX_WARC_DOWNLOADS", "1500000"))
TARGET_RECORDS = int(os.getenv("CC_TARGET_RECORDS", "600000"))
ASYNC_CONCURRENCY = int(os.getenv("CC_ASYNC_CONCURRENCY", "40"))

MIN_TEXT_LENGTH = int(os.getenv("CC_MIN_TEXT_LENGTH", "100"))
MAX_TEXT_LENGTH = int(os.getenv("CC_MAX_TEXT_LENGTH", "10000"))
REQUEST_TIMEOUT = int(os.getenv("CC_REQUEST_TIMEOUT", "45"))

CC_WARC_BASE = "https://data.commoncrawl.org/"

# Deep Historical Coverage (gives us massive runway for an 8hr run)
CC_CRAWL_INDICES = [
    "CC-MAIN-2025-08", "CC-MAIN-2024-51", "CC-MAIN-2024-42", "CC-MAIN-2024-33",
    "CC-MAIN-2024-22", "CC-MAIN-2024-10", "CC-MAIN-2023-50", "CC-MAIN-2023-40",
    "CC-MAIN-2023-23", "CC-MAIN-2023-14", "CC-MAIN-2023-06", "CC-MAIN-2022-49",
    "CC-MAIN-2022-40", "CC-MAIN-2022-33", "CC-MAIN-2022-27", "CC-MAIN-2022-21",
    "CC-MAIN-2022-05", "CC-MAIN-2021-49", "CC-MAIN-2021-43", "CC-MAIN-2021-39",
    "CC-MAIN-2021-31", "CC-MAIN-2021-25", "CC-MAIN-2021-17", "CC-MAIN-2021-10",
    "CC-MAIN-2021-04", "CC-MAIN-2020-50", "CC-MAIN-2020-45", "CC-MAIN-2020-40",
    "CC-MAIN-2020-34", "CC-MAIN-2020-29", "CC-MAIN-2020-24", "CC-MAIN-2020-16",
    "CC-MAIN-2020-10", "CC-MAIN-2020-05", "CC-MAIN-2019-51", "CC-MAIN-2019-47",
    "CC-MAIN-2019-43", "CC-MAIN-2019-39", "CC-MAIN-2019-35", "CC-MAIN-2019-30",
]

EXCLUDED_DOMAINS = frozenset({"phishtank.org", "phishtank.com", "cert.ssi.gouv.fr", "blogs.sap.com", "huggingface.co"})

# ── R2 Storage Configuration ──────────────────────────────────────────
R2_BUCKET = os.getenv("SICURRE_RAW_SNAPSHOT_R2_BUCKET_NAME")
R2_ENDPOINT = os.getenv("SICURRE_RAW_SNAPSHOT_R2_ENDPOINT_URL")
R2_ACCESS_KEY = os.getenv("SICURRE_RAW_SNAPSHOT_R2_ACCESS_KEY_ID")
R2_SECRET_KEY = os.getenv("SICURRE_RAW_SNAPSHOT_R2_SECRET_ACCESS_KEY")
R2_REGION = os.getenv("SICURRE_RAW_SNAPSHOT_R2_REGION", "auto")

# ══════════════════════════════════════════════════════════════════════
# Search Queries
# ══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True, slots=True)
class CrawlQuery:
    pattern: str
    category: str
    label: str

PHISHING_QUERIES = [
    CrawlQuery("signal-arnaques.com/*", "phishing_related", "scam_reports_fr"),
    CrawlQuery("cybermalveillance.gouv.fr/*", "phishing_related", "cert_gov_fr"),
    CrawlQuery("zataz.com/*", "phishing_related", "security_news_fr"),
    CrawlQuery("undernews.fr/*", "phishing_related", "security_news_fr"),
    CrawlQuery("internet-signalement.gouv.fr/*", "phishing_related", "reporting_gov_fr"),
    CrawlQuery("urlscan.io/result/*", "phishing_related", "url_scanning"),
    CrawlQuery("openphish.com/*", "phishing_related", "phishing_feed"),
    CrawlQuery("abuse.ch/*", "phishing_related", "abuse_ch"),
    CrawlQuery("forum.quechoisir.org/*arnaque*", "phishing_related", "consumer_forum_fr"),
    CrawlQuery("forum.quechoisir.org/*phishing*", "phishing_related", "consumer_forum_fr"),
    CrawlQuery("commentcamarche.net/*phishing*", "phishing_related", "tech_forum_fr"),
    CrawlQuery("commentcamarche.net/*arnaque*", "phishing_related", "tech_forum_fr"),
    CrawlQuery("forums.futura-sciences.com/*arnaque*", "phishing_related", "science_forum_fr"),
    CrawlQuery("signal-spam.fr/*", "phishing_related", "signal_spam_fr"),
    CrawlQuery("blog.sekoia.io/*", "phishing_related", "threat_intel_fr"),
    CrawlQuery("therecord.media/*phishing*", "phishing_related", "security_news"),
    CrawlQuery("bleepingcomputer.com/*phishing*", "phishing_related", "security_news"),
]

SPAM_QUERIES = [
    CrawlQuery("*.cdiscount.com/newsletter*", "spam_like", "retail_newsletter_fr"),
    CrawlQuery("*.vente-privee.com/*", "spam_like", "ecommerce_promo_fr"),
    CrawlQuery("*.showroomprive.com/newsletter*", "spam_like", "ecommerce_promo_fr"),
    CrawlQuery("*.dealabs.com/*", "spam_like", "deal_aggregator_fr"),
    CrawlQuery("*.darty.com/newsletter*", "spam_like", "retail_newsletter_fr"),
    CrawlQuery("*.boulanger.com/newsletter*", "spam_like", "retail_newsletter_fr"),
]

LEGITIMATE_QUERIES = [
    CrawlQuery("www.service-public.fr/*", "legitimate", "gov_services_fr"),
    CrawlQuery("www.economie.gouv.fr/*", "legitimate", "gov_economy_fr"),
    CrawlQuery("www.legifrance.gouv.fr/*", "legitimate", "gov_legal_fr"),
    CrawlQuery("www.education.gouv.fr/*", "legitimate", "gov_education_fr"),
    CrawlQuery("travail-emploi.gouv.fr/*", "legitimate", "gov_employment_fr"),
    CrawlQuery("www.interieur.gouv.fr/*", "legitimate", "gov_interior_fr"),
    CrawlQuery("www.ameli.fr/*", "legitimate", "health_insurance_fr"),
    CrawlQuery("www.has-sante.fr/*", "legitimate", "health_authority_fr"),
    CrawlQuery("www.sante.fr/*", "legitimate", "health_portal_fr"),
    CrawlQuery("www.mabanque.bnpparibas/*", "legitimate", "bank_fr"),
    CrawlQuery("www.credit-agricole.fr/*", "legitimate", "bank_fr"),
    CrawlQuery("www.labanquepostale.fr/*", "legitimate", "bank_fr"),
    CrawlQuery("www.societegenerale.fr/*", "legitimate", "bank_fr"),
    CrawlQuery("www.lcl.fr/*", "legitimate", "bank_fr"),
    CrawlQuery("www.edf.fr/*", "legitimate", "utility_fr"),
    CrawlQuery("www.engie.fr/*", "legitimate", "utility_fr"),
    CrawlQuery("www.orange.fr/portail*", "legitimate", "telecom_fr"),
    CrawlQuery("www.free.fr/*", "legitimate", "telecom_fr"),
    CrawlQuery("www.laposte.fr/*", "legitimate", "postal_fr"),
    CrawlQuery("www.colissimo.fr/*", "legitimate", "postal_fr"),
    CrawlQuery("www.chronopost.fr/*", "legitimate", "postal_fr"),
    CrawlQuery("www.caf.fr/*", "legitimate", "social_fr"),
    CrawlQuery("www.urssaf.fr/*", "legitimate", "social_fr"),
    CrawlQuery("www.pole-emploi.fr/*", "legitimate", "social_fr"),
    CrawlQuery("www.info-retraite.fr/*", "legitimate", "social_fr"),
]

# ══════════════════════════════════════════════════════════════════════
# Engine
# ══════════════════════════════════════════════════════════════════════

def is_excluded_domain(url: str) -> bool:
    try:
        domain = url.split("//")[-1].split("/")[0].lower()
        return any(excl in domain for excl in EXCLUDED_DOMAINS)
    except Exception:
        return False

def extract_text_from_html(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style", "meta", "link", "noscript", "nav", "header", "footer", "aside", "iframe"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()

def detect_language(text: str) -> str:
    try:
        return detect(text[:1500])
    except LangDetectException:
        return "unknown"

def get_boto_client():
    if not all([R2_BUCKET, R2_ENDPOINT, R2_ACCESS_KEY, R2_SECRET_KEY]):
        raise ValueError("Missing R2 credentials in .env")
    return boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        region_name=R2_REGION,
    )

@dataclass
class AsyncExtractionTracker:
    total_index_hits: int = 0
    total_downloaded: int = 0
    extracted: int = 0
    download_errors: int = 0
    skipped_short: int = 0
    skipped_duplicate: int = 0
    per_category: dict[str, int] = field(default_factory=dict)
    per_language: dict[str, int] = field(default_factory=dict)
    seen_hashes: set[str] = field(default_factory=set)


async def fetch_index_page(client: httpx.AsyncClient, query: CrawlQuery, crawl_id: str, semaphore: asyncio.Semaphore) -> list[dict]:
    url = f"https://index.commoncrawl.org/{crawl_id}-index"
    params = {"url": query.pattern, "output": "json", "limit": str(MAX_RESULTS_PER_QUERY)}
    
    async with semaphore:
        for attempt in range(4):
            try:
                resp = await client.get(url, params=params)
                if resp.status_code in (503, 429):
                    await asyncio.sleep(2 ** attempt)
                    continue
                resp.raise_for_status()
                records = [json.loads(line) for line in resp.text.strip().split("\n") if line.strip()]
                valid = []
                for r in records:
                    if not is_excluded_domain(r.get("url", "")):
                        r.update({"_category": query.category, "_label": query.label, "_query": query.pattern, "_crawl_id": crawl_id})
                        valid.append(r)
                return valid
            except Exception as exc:
                if attempt == 3:
                    logger.debug(f"Failed query {query.pattern} on {crawl_id} after retries: {exc}")
                await asyncio.sleep(2 ** attempt)
        return []

async def fetch_warc_record(client: httpx.AsyncClient, row: dict, semaphore: asyncio.Semaphore, tracker: AsyncExtractionTracker) -> dict | None:
    if tracker.extracted >= TARGET_RECORDS:
        return None
        
    offset = int(row["offset"])
    end = offset + int(row["length"]) - 1
    url = f"{CC_WARC_BASE}{row['filename']}"
    headers = {"Range": f"bytes={offset}-{end}"}

    async with semaphore:
        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code not in (200, 206):
                tracker.download_errors += 1
                return None
                
            tracker.total_downloaded += 1
            stream = io.BytesIO(resp.content)
            
            for record in ArchiveIterator(stream):
                if record.rec_type != "response":
                    continue
                html = record.content_stream().read().decode("utf-8", errors="replace")
                text = extract_text_from_html(html)
                
                if len(text) < MIN_TEXT_LENGTH:
                    tracker.skipped_short += 1
                    return None
                    
                text = text[:MAX_TEXT_LENGTH]
                c_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
                
                if c_hash in tracker.seen_hashes:
                    tracker.skipped_duplicate += 1
                    return None
                
                tracker.seen_hashes.add(c_hash)
                lang = detect_language(text)
                
                tracker.per_language[lang] = tracker.per_language.get(lang, 0) + 1
                tracker.per_category[row["_category"]] = tracker.per_category.get(row["_category"], 0) + 1
                tracker.extracted += 1
                
                return {
                    "url": row["url"],
                    "text": text,
                    "text_length": len(text),
                    "language": lang,
                    "category": row["_category"],
                    "label": row["_label"],
                    "query": row["_query"],
                    "crawl_id": row["_crawl_id"],
                    "content_hash": c_hash,
                }
        except Exception:
            tracker.download_errors += 1
            return None


async def run_pipeline():
    tracker = AsyncExtractionTracker()
    all_queries = PHISHING_QUERIES + SPAM_QUERIES + LEGITIMATE_QUERIES
    
    logger.info("="*60)
    logger.info(f"ASYNC COMMON CRAWL PIPELINE STARTING")
    logger.info(f"Target Records: {TARGET_RECORDS}")
    logger.info(f"Max Downloads:  {MAX_WARC_DOWNLOADS}")
    logger.info(f"Crawl Indices:  {len(CC_CRAWL_INDICES)} (Deep History enabled)")
    logger.info("="*60)

    # 1. Gather all Index Queries
    logger.info("Phase 1: Concurrently fetching Index APIs...")
    all_records = []
    
    limits = httpx.Limits(max_keepalive_connections=ASYNC_CONCURRENCY, max_connections=ASYNC_CONCURRENCY+10)
    timeout = httpx.Timeout(REQUEST_TIMEOUT)
    
    async with httpx.AsyncClient(limits=limits, timeout=timeout, follow_redirects=True) as client:
        # Common Crawl's small index server WILL 503 if we send 40 parallel requests.
        # So we restrict searching the index to just 3 workers, while WARC downloading uses 40.
        index_semaphore = asyncio.Semaphore(3)
        
        # We query indices dynamically so we don't hold thousands of tasks in memory at once
        # For memory safety, we do it index by index, but concurrent across queries
        for crawl_id in CC_CRAWL_INDICES:
            if len(all_records) > MAX_WARC_DOWNLOADS * 1.5:
                logger.info(f"Sufficient index hits collected ({len(all_records)}). Moving to Phase 2.")
                break
                
            tasks = [fetch_index_page(client, q, crawl_id, index_semaphore) for q in all_queries]
            results = await asyncio.gather(*tasks)
            for res in results:
                all_records.extend(res)
            logger.info(f"Index {crawl_id} -> total hits so far: {len(all_records)}")

    if not all_records:
        logger.error("No raw index hits found.")
        return

    df_index = pd.DataFrame(all_records).drop_duplicates(subset=["url"]).reset_index(drop=True)
    tracker.total_index_hits = len(df_index)
    logger.info(f"Phase 1 Complete. {len(df_index)} unique URLs ready for extraction.")

    # Apply MIME/Status filters if provided by index API
    if "status" in df_index.columns:
        df_index = df_index[df_index["status"].astype(str) == "200"]
    if "mime" in df_index.columns:
        df_index = df_index[df_index["mime"].str.contains("html", case=False, na=False)]

    df_index = df_index.head(MAX_WARC_DOWNLOADS)
    
    # 2. Extract WARC Data Concurrently
    logger.info(f"Phase 2: Concurrently downloading WARC records (Max bounding: {len(df_index)})...")
    extracted_pages = []
    
    async with httpx.AsyncClient(limits=limits, timeout=timeout, follow_redirects=True) as client:
        semaphore = asyncio.Semaphore(ASYNC_CONCURRENCY)
        
        # Batch execution to prevent out-of-memory for millions of asyncio tasks
        batch_size = 5000 
        for idx in range(0, len(df_index), batch_size):
            if tracker.extracted >= TARGET_RECORDS:
                break
                
            batch_rows = df_index.iloc[idx:idx+batch_size].to_dict('records')
            tasks = [fetch_warc_record(client, row, semaphore, tracker) for row in batch_rows]
            
            logger.info(f"  -> Awaiting WARC batch {idx} to {idx+batch_size}...")
            results = await asyncio.gather(*tasks)
            
            for page in results:
                if page:
                    extracted_pages.append(page)
                    
            logger.info(f"  Progress: Downloaded={tracker.total_downloaded}, Extracted={tracker.extracted}")

    # 3. Export directly to R2
    if not extracted_pages:
        logger.warning("No pages extracted to upload.")
        return
        
    logger.info("Phase 3: Uploading datasets directly to Cloudflare R2...")
    df_all = pd.DataFrame(extracted_pages)
    
    df_usable = df_all[
        (df_all["language"] == "fr") & 
        (df_all["text_length"] >= MIN_TEXT_LENGTH)
    ].reset_index(drop=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    
    s3_client = get_boto_client()
    base_prefix = "raw-snapshots/bigdata/common_crawl"

    def upload_df(df, subfolder):
        filename = f"{base_prefix}/{subfolder}/common_crawl_{subfolder}_{len(df)}_{timestamp}.parquet"
        
        # Write to Parquet in-memory buffer using PyArrow
        parquet_buffer = io.BytesIO()
        df.to_parquet(parquet_buffer, index=False, engine="pyarrow")
        
        s3_client.put_object(
            Bucket=R2_BUCKET,
            Key=filename,
            Body=parquet_buffer.getvalue(),
            ContentType="application/vnd.apache.parquet"
        )
        logger.info(f"Uploaded Parquet: r2://{R2_BUCKET}/{filename}")

    # Upload CSVs
    upload_df(df_all, "raw")
    if not df_usable.empty:
        upload_df(df_usable, "fr_usable")

    # Upload Quality Report
    report = {
        "extraction_date": timestamp,
        "config": {
            "async_concurrency": ASYNC_CONCURRENCY,
            "target_records": TARGET_RECORDS,
            "max_warc_downloads": MAX_WARC_DOWNLOADS,
        },
        "stats": {
            "total_index_hits": tracker.total_index_hits,
            "total_downloaded": tracker.total_downloaded,
            "total_extracted": tracker.extracted,
            "download_errors": tracker.download_errors,
            "usable_french": len(df_usable),
        },
        "language_distribution": tracker.per_language,
        "category_distribution": tracker.per_category,
    }
    report_filename = f"{base_prefix}/quality/quality_report_{timestamp}.json"
    s3_client.put_object(
        Bucket=R2_BUCKET,
        Key=report_filename,
        Body=json.dumps(report, indent=2),
        ContentType="application/json"
    )
    logger.info(f"Uploaded Quality Report: r2://{R2_BUCKET}/{report_filename}")

    logger.info("="*60)
    logger.info("PIPELINE COMPLETE - DATA SECURED IN R2")
    logger.info("="*60)

if __name__ == "__main__":
    asyncio.run(run_pipeline())
