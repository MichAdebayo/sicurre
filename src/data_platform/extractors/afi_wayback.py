from __future__ import annotations

import csv
import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import httpx
from bs4 import BeautifulSoup

from core.config import ROOT_DIR

logger = logging.getLogger(__name__)

AFIMode = Literal["french", "all", "stats"]


@dataclass(frozen=True, slots=True)
class AFIWaybackConfig:
    output_dir: Path = ROOT_DIR / "data" / "raw" / "scraping" / "afi_french"
    timeout_seconds: float = 60.0
    connect_timeout_seconds: float = 30.0
    inventory_timeout_seconds: float = 120.0
    base_delay: float = 3.0
    backoff_base: float = 30.0
    max_backoff: float = 300.0
    max_consecutive_errors: int = 5
    progress_log_interval: int = 20
    inventory_min_cached_rows: int = 100

    @property
    def csv_path(self) -> Path:
        return self.output_dir / "afi_french_scam_emails_v2.csv"

    @property
    def progress_path(self) -> Path:
        return self.output_dir / "bulk_progress.json"

    @property
    def inventory_path(self) -> Path:
        return self.output_dir / "all_archived_threads_inventory.json"


@dataclass(slots=True)
class AFIWaybackRunResult:
    mode: AFIMode
    inventory_count: int
    candidate_count: int
    pending_count: int
    completed_count: int
    failed_count: int
    fetched_count: int
    message_count: int
    french_count: int
    error_count: int
    csv_path: Path
    inventory_path: Path
    progress_path: Path
    inventory_language_counts: dict[str, int] = field(default_factory=dict)


class AFIWaybackExtractor:
    def __init__(
        self,
        *,
        config: AFIWaybackConfig | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config or AFIWaybackConfig()
        self.sleep_fn = sleep_fn

    def run(self, mode: AFIMode = "french") -> AFIWaybackRunResult:
        inventory = self.load_inventory()
        progress = self.load_progress()
        inventory_language_counts = self._language_counts(inventory)

        if mode == "stats":
            return self._build_result(
                mode=mode,
                inventory=inventory,
                candidates=inventory,
                pending=[],
                progress=progress,
                inventory_language_counts=inventory_language_counts,
            )

        candidates = self._select_candidates(inventory, mode)
        done_ids = set(progress["completed"]) | set(progress["failed"])
        pending = [
            thread for thread in candidates if thread["thread_id"] not in done_ids
        ]

        logger.info(
            "Mode=%s candidates=%s done=%s pending=%s",
            mode,
            len(candidates),
            len(done_ids),
            len(pending),
        )
        if not pending:
            return self._build_result(
                mode=mode,
                inventory=inventory,
                candidates=candidates,
                pending=pending,
                progress=progress,
                inventory_language_counts=inventory_language_counts,
            )

        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        csv_exists = (
            self.config.csv_path.exists() and self.config.csv_path.stat().st_size > 0
        )

        with self.config.csv_path.open("a", newline="", encoding="utf-8") as csvfile:
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
            client_timeout = httpx.Timeout(
                self.config.timeout_seconds,
                connect=self.config.connect_timeout_seconds,
            )

            try:
                with httpx.Client(
                    timeout=client_timeout, follow_redirects=True
                ) as client:
                    for index, thread in enumerate(pending, start=1):
                        logger.info(
                            "[%s/%s] %s", index, len(pending), thread["slug"][:55]
                        )
                        html = self.fetch_thread(
                            client,
                            timestamp=thread["timestamp"],
                            original=thread["original"],
                        )

                        if html is None:
                            consecutive_errors += 1
                            progress["failed"].append(thread["thread_id"])
                            progress["stats"]["errors"] += 1
                            if consecutive_errors >= self.config.max_consecutive_errors:
                                wait = min(
                                    self.config.backoff_base
                                    * (
                                        2
                                        ** (
                                            consecutive_errors
                                            - self.config.max_consecutive_errors
                                        )
                                    ),
                                    self.config.max_backoff,
                                )
                                logger.warning(
                                    "%s consecutive errors; cooling down %.0fs",
                                    consecutive_errors,
                                    wait,
                                )
                                self.sleep_fn(wait)
                            self.save_progress(progress)
                            self.sleep_fn(self.config.base_delay)
                            continue

                        consecutive_errors = 0
                        progress["stats"]["fetched"] += 1
                        title, messages = self.extract_content(html)
                        if messages:
                            self._write_messages(
                                writer, csvfile, progress, thread, title, messages
                            )

                        progress["completed"].append(thread["thread_id"])
                        self.save_progress(progress)

                        if index % self.config.progress_log_interval == 0:
                            stats = progress["stats"]
                            logger.info(
                                "Progress fetched=%s messages=%s french=%s errors=%s",
                                stats["fetched"],
                                stats["messages"],
                                stats["french"],
                                stats["errors"],
                            )

                        self.sleep_fn(self.config.base_delay)
            except KeyboardInterrupt:
                logger.warning("Interrupted; progress saved.")
                self.save_progress(progress)

        return self._build_result(
            mode=mode,
            inventory=inventory,
            candidates=candidates,
            pending=pending,
            progress=progress,
            inventory_language_counts=inventory_language_counts,
        )

    def load_inventory(self) -> list[dict[str, str]]:
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        if self.config.inventory_path.exists():
            data = json.loads(self.config.inventory_path.read_text(encoding="utf-8"))
            if len(data) > self.config.inventory_min_cached_rows:
                return data

        inventory_url = (
            "https://web.archive.org/cdx/search/cdx"
            "?url=antifraudintl.org/threads/*"
            "&output=text"
            "&fl=timestamp,original,statuscode"
            "&filter=statuscode:200"
            "&collapse=urlkey"
            "&limit=10000"
        )
        response = httpx.get(
            inventory_url,
            timeout=httpx.Timeout(self.config.inventory_timeout_seconds),
            follow_redirects=True,
        )
        response.raise_for_status()
        inventory = self.parse_inventory_payload(response.text)
        self.config.inventory_path.write_text(
            json.dumps(inventory, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return inventory

    def load_progress(self) -> dict[str, Any]:
        if self.config.progress_path.exists():
            return json.loads(self.config.progress_path.read_text(encoding="utf-8"))
        return {
            "completed": [],
            "failed": [],
            "stats": {"fetched": 0, "messages": 0, "french": 0, "errors": 0},
        }

    def save_progress(self, progress: dict[str, Any]) -> None:
        self.config.progress_path.write_text(
            json.dumps(progress, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def fetch_thread(
        self,
        client: httpx.Client,
        *,
        timestamp: str,
        original: str,
        retries: int = 3,
    ) -> str | None:
        wayback_url = f"https://web.archive.org/web/{timestamp}/{original}"
        for attempt in range(retries):
            try:
                response = client.get(wayback_url)
                if response.status_code == 200 and len(response.text) > 3000:
                    return response.text
                if response.status_code == 429:
                    wait = min(
                        self.config.backoff_base * (2**attempt), self.config.max_backoff
                    )
                    logger.warning(
                        "429 rate limit for %s; waiting %.0fs", original, wait
                    )
                    self.sleep_fn(wait)
                    continue
                return None
            except (httpx.ConnectError, ConnectionRefusedError):
                wait = min(
                    self.config.backoff_base * (2**attempt), self.config.max_backoff
                )
                logger.warning(
                    "Connection refused for %s (attempt %s/%s); waiting %.0fs",
                    original,
                    attempt + 1,
                    retries,
                    wait,
                )
                self.sleep_fn(wait)
            except httpx.ReadTimeout:
                logger.warning(
                    "Timeout fetching %s (attempt %s/%s)",
                    original,
                    attempt + 1,
                    retries,
                )
                self.sleep_fn(self.config.base_delay)
            except Exception as exc:
                logger.warning("Unexpected AFI fetch error for %s: %s", original, exc)
                return None
        return None

    @staticmethod
    def classify_slug_language(slug: str) -> str:
        lowered = slug.lower()
        fr_strong = (
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
        )
        fr_moderate = (
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
        )
        en_strong = (
            "-nigerian",
            "-ghana",
            "-scammer",
            "-lottery",
            "dear-sir",
            "attention-",
            "the-",
            "from-the-",
        )

        fr_strong_hits = sum(marker in lowered for marker in fr_strong)
        fr_moderate_hits = sum(marker in lowered for marker in fr_moderate)
        en_strong_hits = sum(marker in lowered for marker in en_strong)

        score = fr_strong_hits * 3 + fr_moderate_hits - en_strong_hits * 2
        if score >= 3:
            return "fr_likely"
        if score >= 1:
            return "fr_possible"
        return "en_likely" if en_strong_hits >= 1 else "unknown"

    @staticmethod
    def detect_french(text: str) -> bool:
        french_markers = (
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
        )
        lowered = text.lower()
        return sum(marker in lowered for marker in french_markers) >= 2

    @staticmethod
    def extract_content(html_text: str) -> tuple[str, list[str]]:
        soup = BeautifulSoup(html_text, "html.parser")
        title_element = soup.select_one(
            "h1.p-title-value, h1 .titleBar, .titleBar h1, .p-title-value"
        )
        title = title_element.get_text(strip=True) if title_element else ""
        if not title:
            fallback_title = soup.select_one("title")
            title = fallback_title.get_text(strip=True) if fallback_title else ""
        title = re.sub(r"\s*\|\s*antifraudintl\.org\s*$", "", title)

        messages: list[str] = []
        for selector in (
            ".bbWrapper",
            "blockquote.messageText",
            ".messageContent .messageText",
            ".message-body .bbWrapper",
            "article.message-body .bbWrapper",
            ".messageContent",
        ):
            elements = soup.select(selector)
            if not elements:
                continue
            for element in elements:
                text = element.get_text(separator="\n", strip=True)
                if len(text) >= 50:
                    messages.append(text)
            if messages:
                break

        return title, messages

    @classmethod
    def parse_inventory_payload(cls, payload: str) -> list[dict[str, str]]:
        threads: list[dict[str, str]] = []
        seen_ids: set[str] = set()
        for line in payload.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            parts = stripped.split(" ")
            if len(parts) < 3:
                continue
            timestamp, original = parts[0], parts[1]
            match = re.search(r"/threads/([^/?#]+\.(\d+))", original)
            if match is None:
                continue
            if "/reply" in original or "/unread" in original or "#" in original:
                continue

            thread_id = match.group(2)
            if thread_id in seen_ids:
                continue
            seen_ids.add(thread_id)
            slug = match.group(1).rstrip("/")
            threads.append(
                {
                    "timestamp": timestamp,
                    "original": original,
                    "slug": slug,
                    "thread_id": thread_id,
                    "slug_lang": cls.classify_slug_language(slug),
                }
            )
        return threads

    def _write_messages(
        self,
        writer: csv.DictWriter[str],
        csvfile: Any,
        progress: dict[str, Any],
        thread: dict[str, str],
        title: str,
        messages: list[str],
    ) -> None:
        for message in messages:
            is_french = self.detect_french(message)
            writer.writerow(
                {
                    "thread_id": thread["thread_id"],
                    "title": title,
                    "body": message,
                    "body_length": len(message),
                    "is_french": is_french,
                    "slug_lang": thread["slug_lang"],
                    "slug": thread["slug"],
                    "wayback_url": (
                        f"https://web.archive.org/web/{thread['timestamp']}/{thread['original']}"
                    ),
                }
            )
            progress["stats"]["messages"] += 1
            if is_french:
                progress["stats"]["french"] += 1
        csvfile.flush()

    def _select_candidates(
        self,
        inventory: list[dict[str, str]],
        mode: AFIMode,
    ) -> list[dict[str, str]]:
        if mode == "french":
            return [
                thread
                for thread in inventory
                if thread["slug_lang"] in ("fr_likely", "fr_possible")
            ]
        if mode == "all":
            return [
                thread for thread in inventory if thread["slug_lang"] != "en_likely"
            ]
        return inventory

    def _language_counts(self, inventory: list[dict[str, str]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for thread in inventory:
            slug_lang = thread["slug_lang"]
            counts[slug_lang] = counts.get(slug_lang, 0) + 1
        return counts

    def _build_result(
        self,
        *,
        mode: AFIMode,
        inventory: list[dict[str, str]],
        candidates: list[dict[str, str]],
        pending: list[dict[str, str]],
        progress: dict[str, Any],
        inventory_language_counts: dict[str, int],
    ) -> AFIWaybackRunResult:
        stats = progress["stats"]
        return AFIWaybackRunResult(
            mode=mode,
            inventory_count=len(inventory),
            candidate_count=len(candidates),
            pending_count=len(pending),
            completed_count=len(progress["completed"]),
            failed_count=len(progress["failed"]),
            fetched_count=stats["fetched"],
            message_count=stats["messages"],
            french_count=stats["french"],
            error_count=stats["errors"],
            csv_path=self.config.csv_path,
            inventory_path=self.config.inventory_path,
            progress_path=self.config.progress_path,
            inventory_language_counts=inventory_language_counts,
        )
