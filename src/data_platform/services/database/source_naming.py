from __future__ import annotations

DATABASE_PARENT_SOURCE = "database-historical"
DATABASE_SOURCE_PREFIX = "database/"


def is_database_source(source_name: str | None) -> bool:
    normalized = str(source_name or "").strip()
    return normalized == DATABASE_PARENT_SOURCE or normalized.startswith(
        DATABASE_SOURCE_PREFIX
    )


def canonical_database_source(source_name: str | None) -> str:
    normalized = str(source_name or "").strip()
    if is_database_source(normalized):
        return DATABASE_PARENT_SOURCE
    return normalized


def database_source_leaf(source_name: str | None) -> str:
    normalized = str(source_name or "").strip().lower()
    if normalized.startswith(DATABASE_SOURCE_PREFIX):
        return normalized.rsplit("/", 1)[-1]
    return normalized


def database_source_family(source_name: str | None) -> str | None:
    normalized = str(source_name or "").strip().lower()
    if not normalized.startswith(DATABASE_SOURCE_PREFIX):
        return None
    parts = normalized.split("/")
    if len(parts) < 3:
        return None
    return parts[1]


def build_database_source_path(source_dataset: str | None) -> str:
    normalized = str(source_dataset or "").strip().lower()
    if not normalized:
        return "database/external/unknown"
    if normalized.startswith(DATABASE_SOURCE_PREFIX):
        return normalized
    if normalized == "adapted_en_fr":
        return f"database/adapted/{normalized}"
    if normalized.startswith("synthetic_") or normalized == "synthetic_append":
        return f"database/faker/{normalized}"
    if normalized.startswith("crowdsourced_"):
        return f"database/crowdsourced/{normalized}"
    return f"database/external/{normalized}"
