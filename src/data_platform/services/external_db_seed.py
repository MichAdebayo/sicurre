from __future__ import annotations

import json
import logging
import random
import re
import uuid
from datetime import datetime, timedelta, timezone

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

from core.config import ROOT_DIR
from data_platform.services.adaptation import FrenchCulturalAdaptationService
from data_platform.services.synthetic_generation import SyntheticGenerationService


logger = logging.getLogger(__name__)
DB_DIR = ROOT_DIR / "data" / "raw" / "db"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "external_threats.db"
DB_URL = f"sqlite:///{DB_PATH}"
CORPUS_PATH = ROOT_DIR / "data" / "raw" / "csv" / "en" / "combined_final_clean.csv"
TXT_DIR = ROOT_DIR / "data" / "raw" / "txt"
SEED = 42
SYNTHETIC_PHISHING_COUNT = 2863


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


def generate_adapted_emails(seed: int = SEED) -> pd.DataFrame:
    if not CORPUS_PATH.exists():
        logger.warning(
            "English corpus not found: %s — skipping adapted emails", CORPUS_PATH
        )
        return pd.DataFrame()
    service = FrenchCulturalAdaptationService(seed=seed)
    source_df = service.load_phishing_corpus(CORPUS_PATH)
    matched_df = service.attach_archetype_matches(source_df)
    generated_df = service.generate_all_adapted_emails(
        matched_df, target_per_archetype=300
    )
    deduplicated_df, removed = service.deduplicate_generated(generated_df)
    logger.info(
        "Adapted emails: %d generated, %d after dedup (%d removed)",
        len(generated_df),
        len(deduplicated_df),
        removed,
    )
    return deduplicated_df


def generate_synthetic_emails(seed: int = SEED) -> pd.DataFrame:
    service = SyntheticGenerationService(seed=seed)
    dataframe = service.generate_class("phishing", SYNTHETIC_PHISHING_COUNT)
    logger.info("Synthetic emails: %d generated", len(dataframe))
    return dataframe


def parse_crowdsourced_spam() -> pd.DataFrame:
    txt_files = sorted(TXT_DIR.glob("Spam_*.txt"))
    if not txt_files:
        logger.warning(
            "No Spam_*.txt files found in %s — skipping crowdsourced spam", TXT_DIR
        )
        return pd.DataFrame()

    rows: list[dict[str, object]] = []
    for txt_path in txt_files:
        raw = txt_path.read_text(encoding="utf-8", errors="replace")
        chunks = re.split(r"(?=^\s{2,}From:\s)", raw, flags=re.MULTILINE)

        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk or not re.match(r"\s*From:", chunk):
                continue
            subject = ""
            date_str = ""
            subject_match = re.search(r"^Subject:\s*(.+)$", chunk, re.MULTILINE)
            date_match = re.search(r"^   Date:\s*(.+)$", chunk, re.MULTILINE)
            if subject_match:
                subject = subject_match.group(1).strip()
            if date_match:
                date_str = date_match.group(1).strip()
            body = ""
            dash_match = re.search(r"^-{3,}.*$", chunk, re.MULTILINE)
            if dash_match:
                body = chunk[dash_match.end() :].strip()
            if not body and not subject:
                continue
            full_text = f"{subject}\n\n{body}" if subject else body
            rows.append(
                {
                    "text": full_text,
                    "label": 0,
                    "source": f"crowdsourced_spam_{txt_path.stem.lower()}",
                    "language": "mixed",
                    "archetype": "",
                    "text_len": len(full_text),
                }
            )

    dataframe = pd.DataFrame(rows)
    logger.info(
        "Crowdsourced spam: %d emails parsed from %d files",
        len(dataframe),
        len(txt_files),
    )
    return dataframe


def redact_pii(text: str) -> str:
    text = re.sub(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
        "[EMAIL]",
        text,
    )
    return re.sub(r"\b0[1-9][ .-]?(?:\d{2}[ .-]?){4}\b", "[PHONE]", text)


def seed_external_database(seed: int = SEED) -> None:
    random.seed(seed)
    fake = Faker("fr_FR")
    Faker.seed(seed)

    dataframes: list[pd.DataFrame] = []
    df_adapted = generate_adapted_emails(seed=seed)
    if not df_adapted.empty:
        dataframes.append(df_adapted)
    df_synthetic = generate_synthetic_emails(seed=seed)
    if not df_synthetic.empty:
        dataframes.append(df_synthetic)
    df_crowdsourced = parse_crowdsourced_spam()
    if not df_crowdsourced.empty:
        dataframes.append(df_crowdsourced)
    if not dataframes:
        logger.error("No data generated. Cannot seed external database.")
        return

    df_emails = pd.concat(dataframes, ignore_index=True)
    logger.info(
        "Combined: %d emails (adapted=%d, synthetic=%d, crowdsourced=%d)",
        len(df_emails),
        len(df_adapted),
        len(df_synthetic),
        len(df_crowdsourced),
    )

    if DB_PATH.exists():
        DB_PATH.unlink()
        logger.info("Removed old external database: %s", DB_PATH)

    engine = create_engine(DB_URL, echo=False)
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine)

    now = datetime.now(timezone.utc)
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
        {
            "version_tag": "v0.1.0",
            "f1_score": 0.89,
            "precision_score": 0.91,
            "recall_score": 0.87,
            "eval_samples": 500,
        },
        {
            "version_tag": "v0.2.0",
            "f1_score": 0.93,
            "precision_score": 0.94,
            "recall_score": 0.92,
            "eval_samples": 1200,
        },
        {
            "version_tag": "v0.3.0",
            "f1_score": 0.96,
            "precision_score": 0.97,
            "recall_score": 0.95,
            "eval_samples": 2000,
        },
    ]

    with session_local() as session:
        user_ids: list[str] = []
        for index in range(10):
            first = fake.first_name()
            last = fake.last_name()
            domain = random.choice(
                ["gmail.com", "outlook.fr", "yahoo.fr", "orange.fr", "free.fr"]
            )
            user = ExternalUser(
                email=f"{first.lower()}.{last.lower()}@{domain}",
                display_name=f"{first} {last}",
                plan=plans[index],
            )
            session.add(user)
            session.flush()
            user_ids.append(str(user.id))

        for model_data in models_data:
            session.add(
                ExternalModelVersion(
                    **model_data,
                    artifact_uri=f"hf://sicurre/camembertv2-phishing-fr:{model_data['version_tag']}",
                )
            )

        threat_ids: list[str] = []
        model_tags = [item["version_tag"] for item in models_data]
        for _, row in df_emails.iterrows():
            user_id = random.choice(user_ids)
            is_phishing = int(row.get("label", 0)) == 1
            confidence = round(
                (
                    random.uniform(0.80, 0.99)
                    if is_phishing
                    else random.uniform(0.50, 0.80)
                ),
                3,
            )
            received_at = now - timedelta(
                days=random.randint(0, 90),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59),
            )
            action_taken = "trashed" if is_phishing and confidence > 0.85 else "none"
            action_at = (
                received_at + timedelta(seconds=random.uniform(0.5, 2.0))
                if action_taken == "trashed"
                else None
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
                received_at=received_at,
                verdict="phishing" if is_phishing else "legitimate",
                confidence=confidence,
                signals=json.dumps(
                    random.choice(phishing_signals) if is_phishing else []
                ),
                archetype=str(row.get("archetype", "")),
                source_dataset=str(row.get("source", "")),
                model_version=random.choice(model_tags),
                action_taken=action_taken,
                action_at=action_at,
            )
            session.add(threat)
            session.flush()
            threat_ids.append(str(threat.id))

        feedback_count = max(30, len(threat_ids) // 10)
        feedback_threats = random.sample(
            threat_ids, min(feedback_count, len(threat_ids))
        )
        for threat_id in feedback_threats:
            session.add(
                ExternalFeedback(
                    threat_log_id=threat_id,
                    user_id=random.choice(user_ids),
                    feedback_label=random.choice(
                        [
                            "true_positive",
                            "false_positive",
                            "false_negative",
                            "true_negative",
                        ]
                    ),
                    comment=random.choice(
                        [
                            None,
                            "Email légitime de ma banque",
                            "C'était bien du phishing URSSAF",
                            "Fausse alerte — newsletter Simplon",
                            "Hameçonnage DGFiP confirmé",
                            "Mon client m'a envoyé cette facture",
                            "Phishing Ameli classique",
                        ]
                    ),
                )
            )

        session.commit()

    logger.info("Seeded %d threat log entries into %s", len(threat_ids), DB_PATH)
    logger.info("  Adapted: %d", len(df_adapted))
    logger.info("  Synthetic: %d", len(df_synthetic))
    logger.info("  Crowdsourced: %d", len(df_crowdsourced))
    logger.info("  Feedback entries: %d", len(feedback_threats))
    logger.info("  Database size: %.1f KB", DB_PATH.stat().st_size / 1024)
