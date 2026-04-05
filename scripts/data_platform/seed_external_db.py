"""
Seed the standalone "external_threats.db" to simulate an enterprise legacy database.

Data sources (all generated/parsed in-memory — no intermediate CSV dependency):
  1. Culturally adapted FR phishing — via FrenchCulturalAdaptationService
  2. Synthetic FR phishing           — via archetype template generator
  3. Crowdsourced spam txt files      — parsed from data/raw/txt/Spam_*.txt

Usage::

    uv run python scripts/data_platform/seed_external_db.py
    # or
    make db-seed
"""

from __future__ import annotations

import json
import logging
import random
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from faker import Faker
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# ── Path setup ────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = ROOT / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(ROOT / "scripts" / "data_platform") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "data_platform"))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────
DB_DIR = ROOT / "data" / "raw" / "db"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "external_threats.db"
DB_URL = f"sqlite:///{DB_PATH}"

CORPUS_PATH = ROOT / "data" / "raw" / "csv" / "en" / "combined_final_clean.csv"
TXT_DIR = ROOT / "data" / "raw" / "txt"

SEED = 42
random.seed(SEED)
fake = Faker("fr_FR")
Faker.seed(SEED)

SYNTHETIC_PHISHING_COUNT = 2863  # Match notebook 11 output volume


# ── External DB Schema (mirrors the legacy monolithic schema) ─────────────
class Base(DeclarativeBase):
    pass


class ExternalUser(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, nullable=False, unique=True)
    display_name = Column(String)
    plan = Column(String, nullable=False, default="free")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ExternalThreatLog(Base):
    __tablename__ = "threat_log"
    __table_args__ = (
        UniqueConstraint("user_id", "message_id", name="uq_user_message"),
    )
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    message_id = Column(String, nullable=False)
    subject = Column(Text)
    body_preview = Column(Text)
    received_at = Column(DateTime)
    verdict = Column(String, nullable=False)
    confidence = Column(Float)
    signals = Column(Text)
    archetype = Column(String)
    source_dataset = Column(String)
    model_version = Column(String, nullable=False)
    action_taken = Column(String)
    action_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ExternalFeedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (
        UniqueConstraint("threat_log_id", "user_id", name="uq_feedback_threat_user"),
    )
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    threat_log_id = Column(String, ForeignKey("threat_log.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    feedback_label = Column(String, nullable=False)
    comment = Column(Text)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ExternalModelVersion(Base):
    __tablename__ = "model_versions"
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    version_tag = Column(String, nullable=False, unique=True)
    artifact_uri = Column(String)
    f1_score = Column(Float)
    precision_score = Column(Float)
    recall_score = Column(Float)
    eval_samples = Column(Integer)
    promoted_at = Column(DateTime)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


# ══════════════════════════════════════════════════════════════════════════
# Data generation — all in-memory, no CSV intermediaries
# ══════════════════════════════════════════════════════════════════════════


def generate_adapted_emails() -> pd.DataFrame:
    """Generate culturally adapted FR phishing emails from the EN corpus.

    Uses FrenchCulturalAdaptationService (ported from Notebook 10).
    """
    from data_platform.services.adaptation import FrenchCulturalAdaptationService

    if not CORPUS_PATH.exists():
        logger.warning("English corpus not found: %s — skipping adapted emails", CORPUS_PATH)
        return pd.DataFrame()

    service = FrenchCulturalAdaptationService(seed=SEED)
    source_df = service.load_phishing_corpus(CORPUS_PATH)
    matched_df = service.attach_archetype_matches(source_df)
    generated_df = service.generate_all_adapted_emails(matched_df, target_per_archetype=300)
    deduplicated_df, removed = service.deduplicate_generated(generated_df)

    logger.info(
        "Adapted emails: %d generated, %d after dedup (%d removed)",
        len(generated_df),
        len(deduplicated_df),
        removed,
    )
    return deduplicated_df


def generate_synthetic_emails() -> pd.DataFrame:
    """Generate synthetic FR phishing emails from archetype templates.

    Uses the archetype JSON + template engine (ported from Notebook 11).
    """
    from generate_synthetic_data import generate_class

    df = generate_class("phishing", SYNTHETIC_PHISHING_COUNT)
    logger.info("Synthetic emails: %d generated", len(df))
    return df


def parse_crowdsourced_spam() -> pd.DataFrame:
    """Parse crowdsourced spam from Spam_*.txt files in data/raw/txt/.

    Each file contains multiple emails separated by '   From:' headers
    with Subject/Date/To metadata followed by a dashed separator line.
    """
    txt_files = sorted(TXT_DIR.glob("Spam_*.txt"))
    if not txt_files:
        logger.warning("No Spam_*.txt files found in %s — skipping crowdsourced spam", TXT_DIR)
        return pd.DataFrame()

    rows: list[dict] = []
    for txt_path in txt_files:
        raw = txt_path.read_text(encoding="utf-8", errors="replace")
        # Split on the "   From:" header that starts each email
        chunks = re.split(r"(?=^\s{2,}From:\s)", raw, flags=re.MULTILINE)

        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk or not re.match(r"\s*From:", chunk):
                continue

            # Extract headers
            subject = ""
            date_str = ""
            subject_match = re.search(r"^Subject:\s*(.+)$", chunk, re.MULTILINE)
            date_match = re.search(r"^   Date:\s*(.+)$", chunk, re.MULTILINE)
            if subject_match:
                subject = subject_match.group(1).strip()
            if date_match:
                date_str = date_match.group(1).strip()

            # Extract body: everything after the first "---" separator line
            body = ""
            dash_match = re.search(r"^-{3,}.*$", chunk, re.MULTILINE)
            if dash_match:
                body = chunk[dash_match.end():].strip()

            if not body and not subject:
                continue

            full_text = f"{subject}\n\n{body}" if subject else body

            rows.append({
                "text": full_text,
                "label": 0,  # spam = 0 (not phishing=1)
                "source": f"crowdsourced_spam_{txt_path.stem.lower()}",
                "language": "mixed",  # EN + FR mix
                "archetype": "",
                "text_len": len(full_text),
            })

    df = pd.DataFrame(rows)
    logger.info(
        "Crowdsourced spam: %d emails parsed from %d files",
        len(df),
        len(txt_files),
    )
    return df


# ══════════════════════════════════════════════════════════════════════════
# DB seeding
# ══════════════════════════════════════════════════════════════════════════


def redact_pii(text: str) -> str:
    """Mask emails and phone numbers for RGPD compliance."""
    text = re.sub(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "[EMAIL]",
        text,
    )
    text = re.sub(r"\b0[1-9][ .-]?(?:\d{2}[ .-]?){4}\b", "[PHONE]", text)
    return text


def main() -> None:
    # ── Generate data in-memory ──────────────────────────────────────────
    dfs: list[pd.DataFrame] = []

    df_adapted = generate_adapted_emails()
    if not df_adapted.empty:
        dfs.append(df_adapted)

    df_synthetic = generate_synthetic_emails()
    if not df_synthetic.empty:
        dfs.append(df_synthetic)

    df_crowdsourced = parse_crowdsourced_spam()
    if not df_crowdsourced.empty:
        dfs.append(df_crowdsourced)

    if not dfs:
        logger.error("No data generated. Cannot seed external database.")
        return

    df_emails = pd.concat(dfs, ignore_index=True)
    logger.info(
        "Combined: %d emails (adapted=%d, synthetic=%d, crowdsourced=%d)\n",
        len(df_emails),
        len(df_adapted),
        len(df_synthetic),
        len(df_crowdsourced),
    )

    # ── Create fresh external database ───────────────────────────────────
    if DB_PATH.exists():
        DB_PATH.unlink()
        logger.info("Removed old external database: %s", DB_PATH)

    engine = create_engine(DB_URL, echo=False)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)

    now = datetime.now(timezone.utc)
    N_USERS = 10
    plans = ["free"] * 4 + ["pro"] * 4 + ["business"] * 2

    phishing_signals = [
        ["DMARC fail", "Suspicious URL"],
        ["SPF fail", "Urgency language"],
        ["Homograph domain", "Credential request"],
        ["URL mismatch", "DKIM fail"],
        ["New sender", "Attachment suspicious"],
        ["Reply-to mismatch", "French impersonation"],
        ["Lookalike domain", "PII request"],
    ]

    models_data = [
        {"version_tag": "v0.1.0", "f1_score": 0.89, "precision_score": 0.91, "recall_score": 0.87, "eval_samples": 500},
        {"version_tag": "v0.2.0", "f1_score": 0.93, "precision_score": 0.94, "recall_score": 0.92, "eval_samples": 1200},
        {"version_tag": "v0.3.0", "f1_score": 0.96, "precision_score": 0.97, "recall_score": 0.95, "eval_samples": 2000},
    ]

    with SessionLocal() as session:
        # ── Users ────────────────────────────────────────────────────────
        user_ids: list[str] = []
        for i in range(N_USERS):
            first = fake.first_name()
            last = fake.last_name()
            domain = random.choice(["gmail.com", "outlook.fr", "yahoo.fr", "orange.fr", "free.fr"])
            user = ExternalUser(
                email=f"{first.lower()}.{last.lower()}@{domain}",
                display_name=f"{first} {last}",
                plan=plans[i],
            )
            session.add(user)
            session.flush()
            user_ids.append(user.id)

        # ── Model versions ───────────────────────────────────────────────
        for md in models_data:
            mv = ExternalModelVersion(
                **md,
                artifact_uri=f"hf://sicurre/camembertv2-phishing-fr:{md['version_tag']}",
            )
            session.add(mv)

        # ── Threat log entries ───────────────────────────────────────────
        model_tags = [m["version_tag"] for m in models_data]
        threat_ids: list[str] = []

        for _idx, row in df_emails.iterrows():
            user_id = random.choice(user_ids)
            is_phishing = int(row.get("label", 0)) == 1
            confidence = round(
                random.uniform(0.80, 0.99) if is_phishing else random.uniform(0.50, 0.80),
                3,
            )

            text = str(row.get("text", ""))
            subject = ""
            body_preview = text[:200]

            if text.startswith("Objet : "):
                parts = text.split("\n\n", 1)
                subject = parts[0].replace("Objet : ", "", 1)
                body_preview = parts[1][:200] if len(parts) > 1 else text[:200]
            elif "\n\n" in text:
                parts = text.split("\n\n", 1)
                subject = parts[0][:200]
                body_preview = parts[1][:200] if len(parts) > 1 else text[:200]

            body_preview = redact_pii(body_preview)

            threat = ExternalThreatLog(
                user_id=user_id,
                message_id=f"msg_{uuid.uuid4().hex[:12]}",
                subject=subject,
                body_preview=body_preview,
                received_at=now - timedelta(
                    days=random.randint(0, 90),
                    hours=random.randint(0, 23),
                    minutes=random.randint(0, 59),
                ),
                verdict="phishing" if is_phishing else "legitimate",
                confidence=confidence,
                signals=json.dumps(
                    random.choice(phishing_signals) if is_phishing else [],
                ),
                archetype=str(row.get("archetype", "")),
                source_dataset=str(row.get("source", "")),
                model_version=random.choice(model_tags),
                action_taken="trashed" if is_phishing and confidence > 0.85 else "none",
            )
            if threat.action_taken == "trashed":
                threat.action_at = threat.received_at + timedelta(
                    seconds=random.uniform(0.5, 2.0),
                )

            session.add(threat)
            session.flush()
            threat_ids.append(threat.id)

        # ── Feedback (10% of threats) ────────────────────────────────────
        feedback_count = max(30, len(threat_ids) // 10)
        feedback_threats = random.sample(
            threat_ids, min(feedback_count, len(threat_ids)),
        )
        for tid in feedback_threats:
            fb = ExternalFeedback(
                threat_log_id=tid,
                user_id=random.choice(user_ids),
                feedback_label=random.choice([
                    "true_positive", "false_positive",
                    "false_negative", "true_negative",
                ]),
                comment=random.choice([
                    None,
                    "Email légitime de ma banque",
                    "C'était bien du phishing URSSAF",
                    "Fausse alerte — newsletter Simplon",
                    "Hameçonnage DGFiP confirmé",
                    "Mon client m'a envoyé cette facture",
                    "Phishing Ameli classique",
                ]),
            )
            session.add(fb)

        session.commit()

    logger.info("Seeded %d threat log entries into %s", len(threat_ids), DB_PATH)
    logger.info("  Adapted: %d", len(df_adapted))
    logger.info("  Synthetic: %d", len(df_synthetic))
    logger.info("  Crowdsourced: %d", len(df_crowdsourced))
    logger.info("  Feedback entries: %d", len(feedback_threats))
    logger.info("  Database size: %.1f KB", DB_PATH.stat().st_size / 1024)


if __name__ == "__main__":
    main()
