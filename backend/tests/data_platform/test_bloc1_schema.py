from __future__ import annotations

from sqlalchemy import create_engine, inspect

from sicurre_api.core.database import Base
from sicurre_api.domains.data_platform.models import lineage  # noqa: F401


def test_bloc1_schema_creates_all_tables() -> None:
    engine = create_engine("sqlite:///:memory:")

    try:
        Base.metadata.create_all(engine)
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
    finally:
        engine.dispose()

    assert table_names == {
        "data_annotation",
        "data_dataset",
        "data_dataset_item",
        "data_ingestion_run",
        "data_normalized_message",
        "data_processing_run",
        "data_raw_object",
        "data_raw_record",
        "data_source_system",
    }
