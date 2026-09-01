"""Connection strings must never reach a log with their password intact.

The scheduled data-platform jobs log which database they connect to, which is
genuinely useful when a job points somewhere unexpected. They were logging the
whole URI, so a live Neon password sat in plaintext in a world-readable cron log
on the production host and was rewritten on every run.
"""

from core.config import redact_database_url


def test_password_is_removed_from_a_postgres_uri() -> None:
    redacted = redact_database_url(
        "postgresql+psycopg://sicurre-data-platform:npg_SuperSecret123"
        "@ep-x.eu-central-1.aws.neon.tech/sicurre_data_platform?sslmode=require"
    )

    assert "npg_SuperSecret123" not in redacted
    assert redacted.startswith("postgresql+psycopg://sicurre-data-platform:***@")


def test_host_user_and_database_survive_so_the_line_stays_useful() -> None:
    """Redaction must not blank the whole URI - knowing the target is the point."""
    redacted = redact_database_url(
        "postgresql://sicurre:pw@ep-lingering-dust.eu-central-1.aws.neon.tech/mydb"
    )

    assert "sicurre" in redacted
    assert "ep-lingering-dust.eu-central-1.aws.neon.tech" in redacted
    assert "mydb" in redacted


def test_password_containing_an_at_sign_is_removed_whole() -> None:
    """A non-greedy match would stop at the first '@' and leak the remainder."""
    redacted = redact_database_url("postgresql://user:p@ss:word@host:5432/db")

    assert "p@ss:word" not in redacted
    assert "ss:word" not in redacted
    assert redacted == "postgresql://user:***@host:5432/db"


def test_credential_free_urls_pass_through_unchanged() -> None:
    sqlite_url = "sqlite+aiosqlite:////home/app/data/local/sicurre.db"

    assert redact_database_url(sqlite_url) == sqlite_url


def test_missing_configuration_is_reported_rather_than_crashing() -> None:
    assert redact_database_url(None) == "(unset)"
    assert redact_database_url("") == "(unset)"
