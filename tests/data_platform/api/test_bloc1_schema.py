from __future__ import annotations

from sqlalchemy import create_engine, inspect

from core.database import Base
from db.models import lineage  # noqa: F401


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
        "data_generation_run",
        "data_generation_sample",
        "data_generation_sample_source_link",
        "data_ingestion_run",
        "data_normalized_message",
        "data_processing_run",
        "data_raw_object",
        "data_raw_record",
        "data_source_system",
        "poc_user",
        "pipeline_state",
    }
