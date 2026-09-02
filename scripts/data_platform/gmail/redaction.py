"""Redaction for real correspondence entering the corpus.

Everything else in the training data is synthetic or public. Real mail is the
first source that carries identifiers belonging to a living person, so it gets
a stricter pass than ``seed.redact_pii``, which only handles addresses and
phone numbers.

The rule followed here is that a redaction failure must be a false positive,
never a false negative: over-redacting costs a little signal, under-redacting
publishes someone's account number. Patterns are therefore deliberately broad.

What is intentionally NOT redacted: the sender organisation, the commercial
content, the structure and register of the message. Those are the entire reason
the mail is useful, and none of them identify a person.
"""

from __future__ import annotations

import re

_EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
#: French mobile/landline, with or without separators, plus +33 form.
_PHONE = re.compile(r"(?:\+33|0)\s?[1-9](?:[\s.\-]?\d{2}){4}\b")
#: Trailing groups of an IBAN can be shorter than four characters; without
#: the optional tail the last group was left in the clear.
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{2,4}){2,8}\b")
#: 13-19 digit card-like runs, grouped or not.
_CARD = re.compile(r"\b(?:\d[ \-]?){13,19}\b")
#: Customer/contract/booking references: a label then an alphanumeric run.
#: A reference token must contain a digit and no whitespace. An earlier version
#: allowed spaces inside the token, which made it greedy: "n° FA-2026-88192 d'un
#: montant" collapsed into "[REF]'un montant", and "Suivi : https://..." ate the
#: URL scheme. Requiring a digit and forbidding spaces keeps the match to the
#: identifier itself.
_REFERENCE = re.compile(
    r"((?:n°|no\.?|num[ée]ro|r[ée]f(?:[ée]rence)?|dossier|contrat|client|"
    r"allocataire|assur[ée]|abonn[ée]|commande|colis|suivi|identifiant)"
    # Up to two words may sit between the label and the value: "Reference
    # transaction : PZ-88192043" leaked when the colon had to follow the label
    # directly.
    r"(?:\s+\w+){0,2}\s*:?\s*)(?!https?://)([A-Za-z0-9][A-Za-z0-9\-/]*\d[A-Za-z0-9\-/]*)",
    re.IGNORECASE,
)
#: French postal address line: number + street type.
_ADDRESS = re.compile(
    r"\b\d{1,4}\s*(?:bis|ter)?\s*,?\s*"
    r"(?:rue|avenue|av\.|boulevard|bd|place|impasse|chemin|all[ée]e|route|quai)\s+"
    r"[A-Za-zÀ-ÿ'\- ]{2,40}",
    re.IGNORECASE,
)
_POSTCODE = re.compile(r"\b\d{5}\s+[A-ZÀ-Ý][A-Za-zÀ-ÿ'\- ]{2,30}\b")
#: Masked card tails: "se terminant par 4417", "carte **** 4417", "finissant
#: par 4417". Not caught by _CARD (too short) or _REFERENCE (no label), and
#: found leaking in a real PayZen receipt during a fixture run. Four digits is
#: not a card number, but it is an identifier tied to a person's payment
#: instrument and has no value as training signal.
_CARD_TAIL = re.compile(
    r"((?:se\s+terminant\s+par|finissant\s+par|terminee?\s+par|xx+|\*{2,})\s*)(\d{4})\b",
    re.IGNORECASE,
)

#: Tracking links dominate real bulk mail. A single CAF newsletter body was
#: ~75% URLs of the form
#:   https://lettreinfo.cafnord.fr/l/6158/800320996/393/76527/1141476/cc03bf2d
#: where every path segment is a per-recipient identifier - the recipient id,
#: the send id, the link id. Keeping them would leak those identifiers, consume
#: most of the token budget, and teach "many tracking URLs = legitimate", which
#: is a shortcut phishing defeats trivially because phishing has URLs too.
#:
#: The host is kept because the sending domain is real signal; the path is not.
_TRACKING_URL = re.compile(r"https?://([A-Za-z0-9.\-]+)/[^\s]*")

#: A line that is nothing but a link, left over after the above.
_BARE_LINK_LINE = re.compile(r"^\s*\[LIEN:[^\]]*\]\s*$", re.MULTILINE)

_URL_QUERY = re.compile(r"(https?://[^\s?]+)\?[^\s]*")


def redact(text: str, *, owner_names: tuple[str, ...] = ()) -> str:
    """Redact personal identifiers from one message body.

    ``owner_names`` are the account holder's own names, which appear in
    salutations and would otherwise be the single most frequent identifier in
    the corpus - and a name the model could learn to associate with
    "legitimate".
    """
    text = _EMAIL.sub("[EMAIL]", text)
    text = _IBAN.sub("[IBAN]", text)
    text = _CARD.sub("[NUMERO]", text)
    text = _CARD_TAIL.sub(r"\1[NUMERO]", text)
    text = _PHONE.sub("[TELEPHONE]", text)
    text = _ADDRESS.sub("[ADRESSE]", text)
    text = _POSTCODE.sub("[CODE_POSTAL] [VILLE]", text)
    # Query strings first: they carry per-recipient identifiers, and stripping
    # them before reference matching stops a label like "Suivi :" swallowing the
    # URL that follows it.
    text = _URL_QUERY.sub(r"\1", text)
    # Collapse tracking links to their host before reference matching, so a
    # label followed by a URL cannot swallow it and the identifiers in the path
    # never reach the corpus.
    text = _TRACKING_URL.sub(lambda m: f"[LIEN:{m.group(1)}]", text)
    text = _BARE_LINK_LINE.sub("", text)
    text = _REFERENCE.sub(r"\1[REF]", text)
    # Bulk mail leaves runs of blank lines once the link lines are gone.
    text = re.sub(r"\n{3,}", "\n\n", text)
    for name in owner_names:
        if len(name) >= 3:
            text = re.sub(rf"\b{re.escape(name)}\b", "[DESTINATAIRE]", text, flags=re.IGNORECASE)
    return text
