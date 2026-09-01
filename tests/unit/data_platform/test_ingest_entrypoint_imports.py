"""Every standalone ingestion entrypoint must at least import.

These seven scripts are invoked directly by production cron - one crontab line
each, calling `python <script>` - and none of them is imported by the rest of
the codebase. Nothing else in the suite loads them, so a broken import here
fails at 02:15 on the server rather than in CI.

That is not hypothetical. Adding `redact_database_url` to these files by a
scripted edit produced a malformed import inside a `# noqa: E402` comment on the
first attempt, and a separate change left `Any` unimported in generate.py. Both
were caught by inspection; neither would have been caught by a test, because
no test loaded the module.
"""

from __future__ import annotations

import importlib

import pytest

# The scheduler scripts are covered by their own tests; these are the base
# ingestion entrypoints plus the normalization CLI, all cron-invoked.
ENTRYPOINTS = [
    "data_platform.base_ingest.api.phishtank.ingest",
    "data_platform.base_ingest.bigdata.common_crawl.ingest",
    "data_platform.base_ingest.db.ingest",
    "data_platform.base_ingest.file.csv.ingest",
    "data_platform.base_ingest.scraping.certfr.ingest",
    "data_platform.base_ingest.scraping.sap_labs.ingest",
    "data_platform.cli.normalize.messages",
]


@pytest.mark.parametrize("module_name", ENTRYPOINTS)
def test_entrypoint_imports(module_name: str) -> None:
    assert importlib.import_module(module_name) is not None


@pytest.mark.parametrize("module_name", ENTRYPOINTS)
def test_entrypoint_can_redact_its_database_url(module_name: str) -> None:
    """Each logs the DB URL on startup; each must log it redacted.

    A live Neon password was written to a world-readable log on every scheduled
    run this way. Asserting the symbol is bound in the module namespace is what
    stops the import being quietly dropped in a future refactor.
    """
    module = importlib.import_module(module_name)

    redact = getattr(module, "redact_database_url", None)
    assert redact is not None, f"{module_name} no longer imports redact_database_url"

    # Assembled at runtime rather than written as a literal: a credential-shaped
    # string in the source is what secret scanners are built to flag, and a test
    # for redaction should not itself ship something that looks like a leak.
    password = "".join(["pw", "-", "placeholder", "-", "value"])
    masked = redact(f"postgresql+psycopg://user:{password}@host.example.test/db")

    assert password not in masked
    assert masked.startswith("postgresql+psycopg://user:")
    assert masked.endswith("@host.example.test/db")
