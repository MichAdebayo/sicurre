from __future__ import annotations

import json
import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any

from faker import Faker
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from data_platform.services.database.cron_scenarios import (
    CRON_ARCHETYPE_SCENARIOS,
    CRON_ARCHETYPE_SCENARIOS_BY_CLASS,
    CronArchetypeScenario,
)
from data_platform.services.database.seed import (
    DB_DIR,
    Base,
    ExternalModelVersion,
    ExternalThreatLog,
    ExternalUser,
    redact_pii,
)
from data_platform.services.database.source_naming import build_database_source_path
from data_platform.services.shared.synthetic_generation import (
    SyntheticGenerationService,
)

DEFAULT_CRON_FEED_DB_PATH = DB_DIR / "external_threats.db"
DEFAULT_CRON_FEED_DB_URL = f"sqlite:///{DEFAULT_CRON_FEED_DB_PATH}"
DEFAULT_CRON_FEED_DB_ASYNC_URL = f"sqlite+aiosqlite:///{DEFAULT_CRON_FEED_DB_PATH}"

DEFAULT_CLASS_COUNTS: dict[str, int] = {
    "phishing": 24,
    "spam": 24,
    "legitimate": 24,
}

_CLASS_CONFIDENCE_RANGES: dict[str, tuple[float, float]] = {
    "phishing": (0.86, 0.99),
    "spam": (0.68, 0.93),
    "legitimate": (0.78, 0.98),
}

_CLASS_SIGNAL_BANKS: dict[str, tuple[tuple[str, ...], ...]] = {
    "phishing": (
        ("DMARC fail", "Urgency language"),
        ("Reply-to mismatch", "Credential request"),
        ("Lookalike domain", "Suspicious payment link"),
        ("SPF fail", "Account suspension pretext"),
        ("Invoice lure", "Brand impersonation"),
    ),
    "spam": (
        ("Promotional CTA", "Newsletter layout"),
        ("Campaign tracking link", "Discount language"),
        ("Affiliate wording", "Unsubscribe footer present"),
        ("Bulk marketing cadence", "Offer countdown"),
        ("Lead-generation copy", "Known sender domain"),
    ),
    "legitimate": (
        ("Known sender domain", "Transactional subject"),
        ("Existing customer context", "Service notification"),
        ("Support thread reference", "Expected account action"),
        ("Billing reference", "Standard help footer"),
        ("Delivery tracking context", "Recognized brand wording"),
    ),
}

_DEFAULT_MODEL_VERSIONS: tuple[dict[str, object], ...] = (
    {
        "version_tag": "v0.1.0",
        "artifact_uri": "hf://sicurre/camembertv2-phishing-fr:v0.1.0",
        "f1_score": 0.89,
        "precision_score": 0.91,
        "recall_score": 0.87,
        "eval_samples": 500,
    },
    {
        "version_tag": "v0.2.0",
        "artifact_uri": "hf://sicurre/camembertv2-phishing-fr:v0.2.0",
        "f1_score": 0.93,
        "precision_score": 0.94,
        "recall_score": 0.92,
        "eval_samples": 1200,
    },
)


@dataclass(frozen=True, slots=True)
class CronExternalDbFeedResult:
    db_url: str
    seed: int
    inserted_total: int
    inserted_by_class: dict[str, int]
    inserted_by_scenario: dict[str, int]
    scenario_catalog_size: int
    used_scenario_count: int


def append_cron_generation_batch(
    *,
    db_url: str | None = None,
    class_counts: dict[str, int] | None = None,
    seed: int | None = None,
) -> CronExternalDbFeedResult:
    effective_counts = dict(DEFAULT_CLASS_COUNTS)
    for class_name, count in (class_counts or {}).items():
        effective_counts[class_name] = count

    unknown_labels = sorted(
        label for label in effective_counts if label not in DEFAULT_CLASS_COUNTS
    )
    if unknown_labels:
        raise ValueError(f"Unsupported labels for cron feed: {unknown_labels}")

    if any(count < 0 for count in effective_counts.values()):
        raise ValueError(f"class counts must be >= 0, got {effective_counts}")
    if sum(effective_counts.values()) <= 0:
        raise ValueError("cron feed requires at least one row to generate")

    effective_url = db_url or DEFAULT_CRON_FEED_DB_URL
    effective_seed = seed if seed is not None else random.randint(0, 2**31 - 1)
    rng = random.Random(effective_seed)
    fake = Faker("fr_FR")
    fake.seed_instance(effective_seed)

    engine = create_engine(effective_url, echo=False)
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine)

    with session_local() as session:
        user_ids = _ensure_users(session, rng, fake)
        model_tags = _ensure_model_versions(session)

        generator = SyntheticGenerationService(seed=effective_seed)
        generated_at = datetime.now(UTC)
        inserted_by_class: dict[str, int] = {}
        inserted_by_scenario: dict[str, int] = {}
        seen_text_hashes: set[str] = set()

        for class_name, count in effective_counts.items():
            if count == 0:
                continue

            dataframe_rows, scenario_counts = _build_cron_rows_for_class(
                generator,
                class_name=class_name,
                count=count,
                rng=rng,
                seen_text_hashes=seen_text_hashes,
            )
            inserted = _append_rows_for_class(
                session,
                dataframe_rows=dataframe_rows,
                class_name=class_name,
                user_ids=user_ids,
                model_tags=model_tags,
                rng=rng,
                generated_at=generated_at,
            )
            inserted_by_class[class_name] = inserted
            inserted_by_scenario.update(scenario_counts)

        session.commit()

    return CronExternalDbFeedResult(
        db_url=effective_url,
        seed=effective_seed,
        inserted_total=sum(inserted_by_class.values()),
        inserted_by_class=inserted_by_class,
        inserted_by_scenario=inserted_by_scenario,
        scenario_catalog_size=len(CRON_ARCHETYPE_SCENARIOS),
        used_scenario_count=len(inserted_by_scenario),
    )


def _build_cron_rows_for_class(
    generator: SyntheticGenerationService,
    *,
    class_name: str,
    count: int,
    rng: random.Random,
    seen_text_hashes: set[str],
) -> tuple[list[dict[str, object]], dict[str, int]]:
    scenarios = list(CRON_ARCHETYPE_SCENARIOS_BY_CLASS[class_name])
    rng.shuffle(scenarios)
    scenario_counts = _allocate_scenario_counts(scenarios, total_count=count)
    archetype_map = _load_archetype_map(generator, class_name)

    rows: list[dict[str, object]] = []
    inserted_by_scenario: dict[str, int] = {}
    for scenario, scenario_count in scenario_counts.items():
        archetype = archetype_map.get(scenario.archetype_id)
        if archetype is None:
            raise ValueError(
                f"Missing static archetype {scenario.archetype_id!r} for {class_name} cron scenario"
            )
        for _ in range(scenario_count):
            rows.append(
                _render_cron_row(
                    generator,
                    archetype=archetype,
                    class_name=class_name,
                    seen_text_hashes=seen_text_hashes,
                    rng=rng,
                )
            )
        inserted_by_scenario[scenario.scenario_id] = scenario_count

    return rows, inserted_by_scenario


def _allocate_scenario_counts(
    scenarios: list[CronArchetypeScenario],
    *,
    total_count: int,
) -> dict[CronArchetypeScenario, int]:
    if total_count <= 0:
        return {}

    if total_count <= len(scenarios):
        return {scenario: 1 for scenario in scenarios[:total_count]}

    counts = {scenario: 1 for scenario in scenarios}
    remaining = total_count - len(scenarios)
    index = 0
    while remaining > 0:
        scenario = scenarios[index % len(scenarios)]
        counts[scenario] += 1
        remaining -= 1
        index += 1
    return counts


def _load_archetype_map(
    generator: SyntheticGenerationService,
    class_name: str,
) -> dict[str, dict[str, Any]]:
    data = generator.load_archetypes(class_name)
    return {
        str(archetype["id"]): archetype
        for archetype in data.get("archetypes", [])
        if isinstance(archetype, dict)
    }


def _render_cron_row(
    generator: SyntheticGenerationService,
    *,
    archetype: dict[str, Any],
    class_name: str,
    seen_text_hashes: set[str],
    rng: random.Random,
) -> dict[str, object]:
    variables = archetype.get("variables") or {}
    templates = list(archetype.get("templates") or ())
    if not templates:
        raise ValueError(f"Archetype {archetype.get('id')!r} has no templates")

    text = ""
    for _ in range(6):
        template = str(rng.choice(templates))
        candidate = generator.render_template(template, variables)
        text_hash = sha256(candidate.encode("utf-8")).hexdigest()
        if text_hash not in seen_text_hashes:
            seen_text_hashes.add(text_hash)
            text = candidate
            break
        text = candidate
    else:
        seen_text_hashes.add(sha256(text.encode("utf-8")).hexdigest())

    tier = str(archetype.get("tier") or "medium")
    return {
        "text": text,
        "label": class_name,
        "source": f"synthetic_{class_name}_{tier}",
        "language": "fr",
        "archetype": str(archetype.get("id") or ""),
        "text_len": len(text),
    }


def _ensure_users(session: Session, rng: random.Random, fake: Faker) -> list[str]:
    user_ids = [str(user.id) for user in session.query(ExternalUser).all()]
    if user_ids:
        return user_ids

    for plan in ("free", "pro", "business"):
        first_name = fake.first_name()
        last_name = fake.last_name()
        domain = rng.choice(("gmail.com", "outlook.fr", "orange.fr", "free.fr"))
        user = ExternalUser(
            email=f"{first_name.lower()}.{last_name.lower()}@{domain}",
            display_name=f"{first_name} {last_name}",
            plan=plan,
        )
        session.add(user)
        session.flush()
        user_ids.append(str(user.id))

    return user_ids


def _ensure_model_versions(session: Session) -> list[str]:
    model_tags = [
        str(model.version_tag) for model in session.query(ExternalModelVersion).all()
    ]
    if model_tags:
        return model_tags

    for model_data in _DEFAULT_MODEL_VERSIONS:
        session.add(ExternalModelVersion(**model_data))
    session.flush()

    return [str(model_data["version_tag"]) for model_data in _DEFAULT_MODEL_VERSIONS]


def _append_rows_for_class(
    session: Session,
    *,
    dataframe_rows: list[dict[str, object]],
    class_name: str,
    user_ids: list[str],
    model_tags: list[str],
    rng: random.Random,
    generated_at: datetime,
) -> int:
    inserted = 0
    for row in dataframe_rows:
        text_content = str(row.get("text", ""))
        subject, body_preview = _split_text_content(text_content)
        confidence = _sample_confidence(class_name, rng)
        received_at = generated_at - timedelta(
            days=rng.randint(0, 14),
            hours=rng.randint(0, 23),
            minutes=rng.randint(0, 59),
        )

        action_taken, action_at = _resolve_action(
            class_name, confidence, received_at, rng
        )
        session.add(
            ExternalThreatLog(
                user_id=rng.choice(user_ids),
                message_id=f"msg_{uuid.uuid4().hex[:12]}",
                subject=subject,
                body_preview=body_preview,
                received_at=received_at,
                verdict=class_name,
                confidence=confidence,
                signals=json.dumps(list(rng.choice(_CLASS_SIGNAL_BANKS[class_name]))),
                archetype=str(row.get("archetype", "")),
                source_dataset=build_database_source_path(str(row.get("source", ""))),
                model_version=rng.choice(model_tags),
                action_taken=action_taken,
                action_at=action_at,
            )
        )
        inserted += 1

    return inserted


def _split_text_content(text_content: str) -> tuple[str, str]:
    subject = ""
    body_preview = text_content[:200]
    if text_content.startswith("Objet : "):
        parts = text_content.split("\n\n", 1)
        subject = parts[0].replace("Objet : ", "", 1)
        body_preview = parts[1][:200] if len(parts) > 1 else text_content[:200]
    elif "\n\n" in text_content:
        parts = text_content.split("\n\n", 1)
        subject = parts[0][:200]
        body_preview = parts[1][:200] if len(parts) > 1 else text_content[:200]

    return subject, redact_pii(body_preview)


def _sample_confidence(class_name: str, rng: random.Random) -> float:
    lower, upper = _CLASS_CONFIDENCE_RANGES[class_name]
    return round(rng.uniform(lower, upper), 3)


def _resolve_action(
    class_name: str,
    confidence: float,
    received_at: datetime,
    rng: random.Random,
) -> tuple[str, datetime | None]:
    match class_name:
        case "phishing":
            action_taken = "trashed" if confidence >= 0.90 else "flagged"
        case "spam":
            action_taken = "flagged" if confidence >= 0.80 else "none"
        case "legitimate":
            action_taken = "none"
        case _:
            action_taken = "none"

    if action_taken == "none":
        return action_taken, None

    return action_taken, received_at + timedelta(seconds=rng.uniform(0.5, 2.0))
