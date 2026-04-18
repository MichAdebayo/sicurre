from __future__ import annotations

from data_platform.services.database.source_naming import (
    build_database_source_path,
    canonical_database_source,
    database_source_family,
    database_source_leaf,
)


def test_build_database_source_path_maps_known_families() -> None:
    assert (
        build_database_source_path("synthetic_phishing_medium")
        == "database/faker/synthetic_phishing_medium"
    )
    assert (
        build_database_source_path("adapted_en_fr") == "database/adapted/adapted_en_fr"
    )
    assert (
        build_database_source_path("crowdsourced_spam_spam_4")
        == "database/crowdsourced/crowdsourced_spam_spam_4"
    )
    assert build_database_source_path("legacy") == "database/external/legacy"


def test_database_source_helpers_extract_canonical_parent_and_leaf() -> None:
    assert (
        canonical_database_source("database/faker/synthetic_phishing_medium")
        == "database-historical"
    )
    assert database_source_family("database/faker/synthetic_phishing_medium") == "faker"
    assert (
        database_source_leaf("database/faker/synthetic_phishing_medium")
        == "synthetic_phishing_medium"
    )
