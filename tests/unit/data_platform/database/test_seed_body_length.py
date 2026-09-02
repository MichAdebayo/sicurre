"""Generated emails must be stored whole, not as their opening paragraph.

seed.py cut every body to 200 characters before storage. The archetype templates
feeding it are 297-611 characters, so all 23,822 synthetic records across the
three classes were kept as their first paragraph and nothing else. The corpus
lost its long-form register entirely: only 189 of 9,851 legitimate examples
(1.9%) were email-length, while real French business mail runs 400-1200.

The rule was also written out twice, which is why the bug existed twice - and
the two copies had already drifted, since only one handled the "Objet : "
prefix. They are now one function, which is what these tests exercise.
"""

from __future__ import annotations

import pytest

from data_platform.services.database.seed import (
    MAX_BODY_CHARS,
    MAX_SUBJECT_CHARS,
    split_subject_and_body,
)

LONG_BODY = (
    "Madame, Monsieur,\n\nDans le cadre de la revue annuelle des dossiers, nos "
    "services ont constate une regularisation vous concernant. Le montant peut "
    "vous etre reverse apres verification de vos coordonnees bancaires. Cette "
    "verification est rendue necessaire par la migration de notre systeme de "
    "paiement vers la nouvelle norme europeenne applicable a compter du mois "
    "prochain, et concerne l'ensemble des beneficiaires enregistres avant cette "
    "date. Nous vous prions d'agreer l'expression de nos salutations distinguees."
)


def test_a_long_body_is_not_truncated_to_a_preview() -> None:
    """The regression, stated directly: 426 characters must not become 200."""
    text = f"Objet : Regularisation de votre dossier\n\n{LONG_BODY}"
    _, body = split_subject_and_body(text)

    assert len(body) > 200, "the body was cut back to a preview"
    assert len(body) == pytest.approx(len(LONG_BODY), abs=2)
    assert body.rstrip().endswith("salutations distinguees.")


def test_the_objet_prefix_is_stripped_from_the_subject() -> None:
    subject, body = split_subject_and_body(f"Objet : Votre facture\n\n{LONG_BODY}")

    assert subject == "Votre facture"
    assert not body.startswith("Objet")


def test_a_plain_first_paragraph_becomes_the_subject() -> None:
    """The second call site never handled the "Objet : " prefix; both do now."""
    subject, body = split_subject_and_body(f"Votre facture\n\n{LONG_BODY}")

    assert subject == "Votre facture"
    assert body.startswith("Madame, Monsieur,")


def test_a_body_with_no_paragraph_break_is_kept_whole() -> None:
    single = "Bonjour, " + "texte " * 80
    subject, body = split_subject_and_body(single)

    assert subject == ""
    assert len(body) == len(single)


def test_subjects_stay_bounded_even_though_bodies_do_not() -> None:
    """A subject is genuinely bounded; letting it grow moves the problem."""
    subject, _ = split_subject_and_body("S" * 5_000 + "\n\n" + LONG_BODY)

    assert len(subject) == MAX_SUBJECT_CHARS
    assert MAX_SUBJECT_CHARS < MAX_BODY_CHARS


def test_a_pathological_body_is_still_bounded() -> None:
    subject, body = split_subject_and_body("Objet : X\n\n" + "b" * (MAX_BODY_CHARS * 3))

    assert len(body) == MAX_BODY_CHARS


def test_personal_identifiers_are_still_redacted() -> None:
    """Lifting the length bound must not lift the redaction with it."""
    _, body = split_subject_and_body(
        "Objet : Facture\n\nContactez-nous a service@exemple.fr ou au 06 12 34 56 78."
    )

    assert "service@exemple.fr" not in body
    assert "06 12 34 56 78" not in body


@pytest.mark.parametrize("value", ["", None])
def test_empty_input_does_not_raise(value: str | None) -> None:
    assert split_subject_and_body(value) == ("", "")
