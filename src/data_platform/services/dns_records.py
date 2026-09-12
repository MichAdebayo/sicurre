"""SPF, DKIM and DMARC record logic shared by onboarding, setup and teardown.

Pure functions over record strings. Nothing here talks to DNS or to
Cloudflare; the callers read the zone and apply what these return.
"""

from __future__ import annotations

import re
from typing import Any


def clean_str(val: str) -> str:
    if not val:
        return ""
    val = val.strip()
    if val.startswith("b'") or val.startswith('b"'):
        val = val[2:-1]
    return val


#: The only include Email Routing needs. ``spf.cloudflare.com`` publishes no
#: SPF record and a missing include target is a permerror under RFC 7208;
#: each include also costs one of the ten DNS lookups a record is allowed.
CLOUDFLARE_ROUTING_INCLUDE = "include:_spf.mx.cloudflare.net"

#: Mechanisms Sicurre has published in the past and now withdraws. Only ever
#: strings Sicurre itself injected - a customer's own includes are untouchable.
WITHDRAWN_SPF_INCLUDES = ("include:spf.cloudflare.com", "include:sicurre.com")

#: A record created from nothing keeps softfail. Sicurre cannot see whose
#: newsletter or invoicing tool also sends for this domain, and `-all` would
#: have receivers reject that mail outright. Tightening to `-all` is the
#: customer's call once they know their own senders; an existing `all` is
#: always preserved, so a domain that already chose `-all` keeps it.
DEFAULT_ALL = "~all"


def merge_spf(current_spf: str) -> str:
    cleaned = clean_str(current_spf)
    parts = cleaned.split()
    if not parts or parts[0] != "v=spf1":
        return f"v=spf1 {CLOUDFLARE_ROUTING_INCLUDE} {DEFAULT_ALL}"

    mechanisms: list[str] = []
    all_mechanism = DEFAULT_ALL
    for mechanism in parts[1:]:
        if mechanism in ("-all", "~all", "?all", "+all"):
            all_mechanism = mechanism
        elif mechanism in WITHDRAWN_SPF_INCLUDES:
            continue
        elif mechanism not in mechanisms:
            mechanisms.append(mechanism)

    if CLOUDFLARE_ROUTING_INCLUDE not in mechanisms:
        mechanisms.append(CLOUDFLARE_ROUTING_INCLUDE)

    return f"v=spf1 {' '.join(mechanisms)} {all_mechanism}"


def has_usable_dkim(content: str) -> bool:
    """True when a DKIM record carries a real public key.

    A genuine RSA public key is a few hundred base64 characters; a short
    placeholder or an empty ``p=`` (a revoked key) is rejected.
    """
    if "v=dkim1" not in content.lower():
        return False
    match = re.search(r"p=([A-Za-z0-9+/=]*)", content)
    return bool(match) and len(match.group(1)) >= 100


def read_dns_state(dns_records: list[dict[str, Any]], zone_name: str) -> tuple[str, str, str]:
    """Pick the SPF, DKIM and DMARC records out of a zone's TXT records.

    Returns the raw content of each, or "" when absent. An apex TXT record
    counts as SPF only when it starts with ``v=spf1``; other apex records
    (provider verification tokens) are ignored. Shared by the setup route and
    the DNS sync.
    """
    spf = dkim = dmarc = ""
    zone = zone_name.lower().rstrip(".")
    for rec in dns_records:
        if rec.get("type") != "TXT":
            continue
        name = clean_str(rec.get("name", "")).lower().rstrip(".")
        content = clean_str(rec.get("content", "")).strip('"')
        if name == zone and content.lower().startswith("v=spf1"):
            spf = content
        elif "._domainkey." in name or name.startswith("_domainkey."):
            if has_usable_dkim(content):
                dkim = content
        elif name == f"_dmarc.{zone}":
            dmarc = content
    return spf, dkim, dmarc


def merge_dmarc(current_dmarc: str) -> str:
    cleaned = clean_str(current_dmarc)
    if not cleaned:
        return "v=DMARC1; p=reject; rua=mailto:dmarc@sicurre.com"

    policy = "quarantine"
    if "p=reject" in cleaned:
        policy = "reject"

    rec = re.sub(r"p=[^;]+", f"p={policy}", cleaned)

    if "rua=" in rec:
        if "dmarc@sicurre.com" not in rec:
            rec = re.sub(r"(rua=[^;'\"]+)", r"\1,mailto:dmarc@sicurre.com", rec)
    else:
        rec = rec.rstrip("; ") + "; rua=mailto:dmarc@sicurre.com"

    return rec


SICURRE_DMARC_MAILBOX = "dmarc@sicurre.com"


def withdraw_dmarc_reporting(current_dmarc: str) -> str | None:
    """Take Sicurre's reporting address out of a customer's DMARC record.

    Returns the rewritten record, or None when it contains nothing of ours.
    The policy tag is never changed and the record is never deleted; only
    Sicurre's mailbox is removed from ``rua`` and ``ruf``.
    """
    cleaned = clean_str(current_dmarc)
    if not cleaned or SICURRE_DMARC_MAILBOX not in cleaned.lower():
        return None

    rebuilt: list[str] = []
    for tag in cleaned.split(";"):
        tag = tag.strip()
        if not tag:
            continue
        name, separator, value = tag.partition("=")
        if not separator or name.strip().lower() not in ("rua", "ruf"):
            rebuilt.append(tag)
            continue
        kept = [
            uri.strip()
            for uri in value.split(",")
            if uri.strip() and SICURRE_DMARC_MAILBOX not in uri.strip().lower()
        ]
        # A reporting tag with no addresses left is dropped, not left empty.
        if kept:
            rebuilt.append(f"{name.strip()}={','.join(kept)}")

    return "; ".join(rebuilt)


def planned_change(current: str, proposed: str) -> str:
    """What connecting would do to one record: add it, change it, or nothing.

    Computed from the same merge the write path uses, so the preview cannot
    promise something different from what is applied.
    """
    if not clean_str(current):
        return "add"
    return "modify" if clean_str(current) != clean_str(proposed) else "keep"
