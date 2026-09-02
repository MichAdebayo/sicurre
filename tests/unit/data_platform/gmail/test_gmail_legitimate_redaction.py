"""Real correspondence is the first corpus source carrying a person's identifiers.

Everything else is synthetic or public. These tests fix the rule that a
redaction failure must be a false positive, never a false negative, and pin the
four leaks found while building the extractor against a realistic fixture -
each of which a synthetic corpus would never have produced:

  * a card tail ("se terminant par 4417"), too short for the card pattern and
    unlabelled, so neither rule caught it
  * a transaction reference behind an intervening word ("Reference transaction
    : PZ-88192043"), where the pattern required the colon to follow the label
  * a greedy reference match that swallowed following prose
  * a label ("Suivi :") that consumed the URL scheme after it
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts/data_platform/gmail"))
from make_legitimate_dropzone import group_for, to_block  # noqa: E402
from redaction import redact  # noqa: E402

OWNER = ("Michael Adebayo", "Adebayo", "Michael")


@pytest.mark.parametrize(
    "raw,leaked",
    [
        ("carte bancaire se terminant par 4417", "4417"),
        ("Reference transaction : PZ-88192043", "88192043"),
        ("numero allocataire 7719204 et votre mot de passe", "7719204"),
        ("IBAN : FR76 3000 4000 0300 1234 5678 912", "5678"),
        ("Contact : service@exemple.fr", "service@exemple.fr"),
        ("au 06 12 34 56 78 du lundi au vendredi", "06 12 34 56 78"),
        ("Adresse : 12 rue des Lilas, 59000 Lille", "rue des Lilas"),
    ],
)
def test_identifiers_do_not_survive(raw: str, leaked: str) -> None:
    assert leaked not in redact(raw, owner_names=OWNER)


def test_the_account_holder_name_is_removed() -> None:
    """It is the single most frequent identifier, and the model could learn it."""
    out = redact("Bonjour Michael Adebayo, votre commande est prete.", owner_names=OWNER)
    assert "Michael" not in out and "Adebayo" not in out
    assert "votre commande est prete" in out


def test_redaction_preserves_the_register() -> None:
    """Over-redaction costs the signal the mail was collected for."""
    out = redact(
        "Montant : 49,90 EUR. En cas de contestation, vous disposez d'un delai "
        "de treize mois a compter de la date de l'operation.",
        owner_names=OWNER,
    )
    assert "49,90 EUR" in out
    assert "delai de treize mois" in out


def test_a_reference_match_does_not_swallow_the_prose_after_it() -> None:
    out = redact("facture n° FA-2026-88192 d'un montant de 49,90 EUR", owner_names=OWNER)
    assert "88192" not in out
    assert "d'un montant de 49,90 EUR" in out


def test_a_label_does_not_consume_a_following_url() -> None:
    """The label survives and the link collapses to its host, not to ``[REF]``.

    ``Suivi :`` is a reference label, so the risk is ``_REFERENCE`` matching
    across the colon and swallowing the link behind a ``[REF]``. It must not:
    the link is handled by ``_TRACKING_URL`` first, which keeps the sending
    host (real signal) and drops the path (per-recipient identifiers).
    """
    out = redact("Suivi : https://exemple.fr/suivi?uid=abc123", owner_names=OWNER)
    assert out.startswith("Suivi : "), "the label itself must survive"
    assert "[LIEN:exemple.fr]" in out, "the host is kept as signal"
    assert "[REF]" not in out, "the reference pattern must not swallow the link"
    assert "uid=abc123" not in out, "tracking parameters identify the recipient"
    assert "/suivi" not in out, "the path carries per-recipient identifiers"


@pytest.mark.parametrize(
    "sender,expected",
    [
        ("CAF@lettreinfo.cafnord.fr", "institutionnel"),
        ("do_not_reply@payzen.eu", "transactionnel"),
        ("no-reply@doctolib.fr", "sante"),
        ("lcl@infos.lcl.fr", "bancaire_assurance"),
    ],
)
def test_allowlisted_senders_resolve_to_a_register(sender: str, expected: str) -> None:
    assert group_for(sender) == expected


@pytest.mark.parametrize(
    "sender",
    [
        "notifications@github.com",
        "jobalerts-noreply@linkedin.com",
        "afriend@gmail.com",
        "no-reply@mail.sicurre.com",
        "paleos@groupes.renater.fr",
    ],
)
def test_personal_and_self_generated_senders_are_excluded(sender: str) -> None:
    """Excluded by construction, not by filtering.

    GitHub notifications dominate category:updates and would put private
    repository names into a published corpus; gmail.com senders are personal
    correspondence from people who did not consent.
    """
    assert group_for(sender) is None


def test_the_emitted_block_parses_back_as_legitimate_french() -> None:
    """The extractor and the dropzone parser must agree on the format."""
    from data_platform.base_ingest.file.parsers.txt_email_ingestion import (
        parse_txt_emails_from_bytes,
    )

    body = (
        "Bonjour,\n\nVotre attestation de paiement est disponible dans votre espace "
        "personnel. Ce document recapitule les prestations versees ainsi que les "
        "periodes concernees, et peut vous etre demande par un bailleur.\n\n"
        "Cordialement,\nCaisse d'Allocations Familiales"
    )
    block = to_block("CAF@lettreinfo.cafnord.fr", "Votre attestation", body)
    records = parse_txt_emails_from_bytes(block.encode("utf-8"), "legitimate_1")

    assert len(records) == 1
    assert records[0].label == "legitimate"
    assert records[0].language == "fr"


def test_the_denylist_wins_over_the_allowlist() -> None:
    """Precedence is the denylist's whole purpose, and it needs its own test.

    Excluding gmail.com senders passes trivially today because no allow group
    matches them either - so a test using such a sender verifies the allowlist
    and says nothing about the denylist. This constructs the case that actually
    distinguishes them: a sender matching an allowed domain that is also denied.
    A future allowlist entry could easily overlap a denied domain, and then
    ordering is the only thing preventing personal mail entering the corpus.
    """
    import make_legitimate_dropzone as mod

    original = mod.SENDER_GROUPS
    try:
        mod.SENDER_GROUPS = {"institutionnel": ("github.com",)}
        assert mod.group_for("someone@notifications.github.com") is None, (
            "a denied sender was admitted because it matched an allow group"
        )
    finally:
        mod.SENDER_GROUPS = original


def test_the_extractor_module_is_actually_committed() -> None:
    """A test that imports an ignored file passes locally and fails in CI.

    .gitignore carries a broad ``build*.py`` rule. The first version of the
    extractor was named build_legitimate_dropzone.py, was silently skipped by
    ``git add -A``, and reached CI as a ModuleNotFoundError - after the pull
    request had already been merged, because the failing check was not read
    before merging.
    """
    import subprocess

    root = Path(__file__).resolve().parents[4]
    for name in ("make_legitimate_dropzone.py", "redaction.py"):
        path = f"scripts/data_platform/gmail/{name}"
        assert (root / path).exists(), f"{path} is missing"
        ignored = subprocess.run(
            ["git", "check-ignore", path], cwd=root, capture_output=True
        )
        assert ignored.returncode != 0, (
            f"{path} is gitignored, so it will not reach CI even though the "
            f"tests importing it pass locally"
        )
