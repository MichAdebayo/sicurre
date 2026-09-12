"""Read what public DNS says about a domain before any Cloudflare token exists.

Used by the onboarding preview: nameservers (is the zone on Cloudflare),
MX hosts (who receives the mail today), and the apex SPF, DMARC and a known
DKIM selector. Nothing here writes, and nothing needs credentials.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass, field

CLOUDFLARE_NS_SUFFIX = ".ns.cloudflare.com"
CLOUDFLARE_MX_SUFFIX = "mx.cloudflare.net"
DKIM_SELECTORS = ("cf2024-1", "google", "selector1", "selector2", "default", "k1", "mail")
_HOSTNAME = re.compile(r"^(?=.{1,253}$)(?!-)([a-z0-9-]{1,63}(?<!-)\.)+[a-z]{2,63}$")

Resolver = Callable[[str, str], list[str]]


@dataclass
class PublicDnsSnapshot:
    """What public DNS returned for a zone; empty strings and lists when absent."""

    zone: str
    resolvable: bool
    nameservers: list[str] = field(default_factory=list)
    mx_hosts: list[str] = field(default_factory=list)
    spf: str = ""
    dmarc: str = ""
    dkim_present: bool = False

    @property
    def on_cloudflare(self) -> bool:
        return any(ns.endswith(CLOUDFLARE_NS_SUFFIX) for ns in self.nameservers)

    @property
    def mail_provider(self) -> str:
        """``cloudflare``, ``other`` or ``none`` depending on the MX hosts."""
        if any(_is_cloudflare_mx(host) for host in self.mx_hosts):
            return "cloudflare"
        return "other" if self.mx_hosts else "none"


def normalize_zone(value: str) -> str | None:
    """Lower-case, strip a trailing dot, and refuse anything that is not a hostname."""
    zone = value.strip().lower().rstrip(".")
    return zone if _HOSTNAME.match(zone) else None


def _is_cloudflare_mx(host: str) -> bool:
    host = host.lower().rstrip(".")
    return host == CLOUDFLARE_MX_SUFFIX or host.endswith(f".{CLOUDFLARE_MX_SUFFIX}")


def _default_resolver(name: str, rrtype: str) -> list[str]:
    import dns.resolver

    answers = dns.resolver.resolve(name, rrtype)
    values: list[str] = []
    for rdata in answers:
        if rrtype == "TXT":
            values.append("".join(part.decode() for part in rdata.strings))
        elif rrtype == "MX":
            values.append(str(rdata.exchange).rstrip("."))
        else:
            values.append(str(rdata).rstrip("."))
    return values


def _lookup(resolve: Resolver, name: str, rrtype: str) -> list[str]:
    try:
        return resolve(name, rrtype)
    except Exception:  # noqa: BLE001 - absence and failure both read as "nothing published"
        return []


def read_public_dns_sync(zone: str, resolve: Resolver | None = None) -> PublicDnsSnapshot:
    """Resolve NS, MX, SPF, DMARC and a DKIM selector for ``zone``.

    ``resolve(name, rrtype)`` returns the record values as strings and may
    raise for a missing name; tests inject it. A zone with no NS answer is
    reported as unresolvable and nothing else is looked up.
    """
    resolve = resolve or _default_resolver
    nameservers = [ns.lower() for ns in _lookup(resolve, zone, "NS")]
    if not nameservers:
        return PublicDnsSnapshot(zone=zone, resolvable=False)
    mx_hosts = sorted({host.lower() for host in _lookup(resolve, zone, "MX")})
    spf = next((txt for txt in _lookup(resolve, zone, "TXT") if txt.lower().startswith("v=spf1")), "")
    dmarc = next(
        (txt for txt in _lookup(resolve, f"_dmarc.{zone}", "TXT") if txt.lower().startswith("v=dmarc1")),
        "",
    )
    dkim_present = any(
        any("v=dkim1" in txt.lower() for txt in _lookup(resolve, f"{selector}._domainkey.{zone}", "TXT"))
        for selector in DKIM_SELECTORS
    )
    return PublicDnsSnapshot(
        zone=zone,
        resolvable=True,
        nameservers=nameservers,
        mx_hosts=mx_hosts,
        spf=spf,
        dmarc=dmarc,
        dkim_present=dkim_present,
    )


async def read_public_dns(zone: str, resolve: Resolver | None = None) -> PublicDnsSnapshot:
    """Async wrapper: the resolver is blocking, so it runs in a thread."""
    return await asyncio.to_thread(read_public_dns_sync, zone, resolve)
