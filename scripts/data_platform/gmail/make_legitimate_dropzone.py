"""Build a legitimate_*.txt dropzone file from real French institutional mail.

The legitimate class is the corpus's weakest: 9,851 examples of which only 189
(1.9%) are email-length. 39% are SMS "ham" with a median of 64 characters, and
55% are Faker templates. There is almost no genuine French institutional
correspondence - which is precisely the register the model misreads as phishing.

This selects by SENDER, not by category sweep, for three reasons. It gives a
defensible provenance statement ("legitimate mail from N identified French
organisations"). It excludes personal correspondence by construction rather than
by filtering. And it keeps out the account holder's own GitHub notifications,
which dominate category:updates and would leak private repository names into a
published corpus.

Dry run by default. Nothing is written without --write.

Named make_ rather than build_ because .gitignore carries a broad ``build*.py``
rule: the first version of this file was silently skipped by ``git add -A`` and
reached CI as a ModuleNotFoundError in the test that imports it.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from redaction import redact  # noqa: E402

#: Senders grouped by register. Chosen because these are the organisations
#: French phishing impersonates: a genuine CAF notice and a fake one differ in
#: ways the model has never had examples of.
SENDER_GROUPS: dict[str, tuple[str, ...]] = {
    "institutionnel": (
        "cafnord.fr", "laposte.fr", "espace-citoyens.net", "sips-services.com",
        "ameli.fr", "impots.gouv.fr", "urssaf.fr", "service-public.fr",
        "francetravail.fr", "pole-emploi.fr", "simplon.co",
    ),
    "bancaire_assurance": (
        "lcl.fr", "ca-pacifica.fr", "profils.org", "contact-mma.fr",
        "contact-adh-assurances.fr", "paypal.fr", "credit-agricole.fr",
        "societegenerale.fr", "bnpparibas.com",
    ),
    "transactionnel": (
        "payzen.eu", "limonetik.com", "fnac.com", "photomaton.com",
    ),
    "sante": ("doctolib.fr",),
    "transport_commerce": (
        "sncf-connect.com", "ouigo-news.com", "enews-airfrance.com",
        "ryanairemail.com", "news.chaussea.com", "official.asos.com",
        "fr-mail.canalplus.com", "email.rowenta.fr", "news.mint-energie.com",
    ),
    "professionnel": ("malt.com", "mail.michaelpage.fr", "talent-soft.com"),
}

#: Never ingest, whatever else matches. The account holder's own automation and
#: personal correspondence.
DENY_SUBSTRINGS = (
    "github.com", "noreply.github.com", "linkedin.com", "gmail.com",
    "vinse.app", "sicurre.com", "renater.fr",
)

OWNER_NAMES = ("Michael Adebayo", "Adebayo Michael", "Michael babatunde", "Adebayo", "Michael")

MIN_CHARS = 250
MAX_CHARS = 4_000


def group_for(sender: str) -> str | None:
    low = sender.lower()
    if any(d in low for d in DENY_SUBSTRINGS):
        return None
    for group, domains in SENDER_GROUPS.items():
        if any(d in low for d in domains):
            return group
    return None


def to_block(sender: str, subject: str, body: str) -> str:
    """One record in the dropzone format the TXT parser expects."""
    return (
        f"   From: {sender}\n"
        f"     To: [DESTINATAIRE]\n"
        f"Subject: {subject}\n"
        f"{'-' * 64}\n"
        f"{body}\n"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path,
                    help="JSON list of {sender, subject, body} harvested from Gmail")
    ap.add_argument("--out", type=Path, default=Path("data/dropzone/legitimate_1.txt"))
    ap.add_argument("--write", action="store_true", help="write the file (default: report only)")
    args = ap.parse_args()

    messages = json.loads(args.input.read_text(encoding="utf-8"))

    kept: list[str] = []
    by_group: Counter[str] = Counter()
    by_sender: Counter[str] = Counter()
    dropped: Counter[str] = Counter()

    try:
        from langdetect import DetectorFactory, detect

        DetectorFactory.seed = 0
    except ImportError:  # pragma: no cover
        print("langdetect unavailable", file=sys.stderr)
        raise SystemExit(1) from None

    for m in messages:
        sender = str(m.get("sender", "")).strip()
        subject = " ".join(str(m.get("subject", "")).split())
        body = str(m.get("body", ""))

        group = group_for(sender)
        if group is None:
            dropped["sender not in allowlist"] += 1
            continue

        body = redact(body, owner_names=OWNER_NAMES)
        subject = redact(subject, owner_names=OWNER_NAMES)
        body = "\n".join(line.rstrip() for line in body.splitlines() if line.strip())

        if len(body) < MIN_CHARS:
            dropped["shorter than MIN_CHARS"] += 1
            continue
        body = body[:MAX_CHARS]

        try:
            if detect(body[:1500]) != "fr":
                dropped["not French"] += 1
                continue
        except Exception:
            dropped["language undetectable"] += 1
            continue

        kept.append(to_block(sender, subject, body))
        by_group[group] += 1
        by_sender[sender] += 1

    print(f"input messages     : {len(messages):,}")
    print(f"kept               : {len(kept):,}")
    print("\ndropped:")
    for reason, n in dropped.most_common():
        print(f"  {n:>6,}  {reason}")
    print("\nkept by register:")
    for group, n in by_group.most_common():
        print(f"  {n:>6,}  {group}")
    print(f"\ndistinct senders kept: {len(by_sender)}")
    for sender, n in by_sender.most_common(15):
        print(f"  {n:>5,}  {sender}")

    if not args.write:
        print("\n(dry run - pass --write to produce the file)")
        return
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(kept), encoding="utf-8")
    print(f"\nwrote {args.out}  ({args.out.stat().st_size:,} bytes, {len(kept):,} records)")


if __name__ == "__main__":
    main()
