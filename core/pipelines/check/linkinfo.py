"""The 'Links' panel: what we found out about each link in the message, in the reply language.

Built only from what the checks already established (Findings), plus the free local domain check for a link the checks did not reach. Nothing is
fetched here, and nothing here changes the verdict."""
from __future__ import annotations

import re

from core.domain.schemas import LinkInfo
from core.lang.i18n import tr, why as why_text

from .ingest import Ingested
from .knowledge import SHORTENERS
from .tools import Findings, _host_of_url, domain_check

MAX_LINKS = 6
_IMITATES = re.compile(r"^imitates (?P<brand>.+) but is not (?P<official>.+)$")


def _age_note(days: int, T) -> str:
    return T("Registered {n} days ago", n=days) if days < 365 else T("Registered about {n} years ago", n=days // 365)


def build(ing: Ingested, f: Findings, reply: str) -> list[LinkInfo]:
    """One LinkInfo per link, in the order they appear, each short link followed by the place it leads to."""
    T = lambda s, **kw: tr(s, reply, **kw)  # noqa: E731
    order: list[str] = []
    for h in ing.entities.hosts[:MAX_LINKS]:
        order.append(h)
        order += [d for d, via in f.via.items() if _host_of_url(via) == h and d not in order]
    for h in f.hosts:  # anything else the checks learned about
        if h not in order:
            order.append(h)
    out: list[LinkInfo] = []
    for host in order[:MAX_LINKS]:
        hard, soft = f.hard_hosts.get(host), f.soft_hosts.get(host)
        if ("domain_check", host) not in f.done and host not in f.official_hosts and not hard and not soft:
            local = domain_check(host)  # free and local, for a link the checks did not reach
            hard, soft = local["hard"] or None, local["soft"] or None
            official = local["official"]
        else:
            official = f.official_hosts.get(host)
        age, dns = f.ages.get(host), f.dns.get(host)
        cert = f.certs.get(host) if age is None else None  # the certificate log stands in for the registry only when the registry said nothing
        listed = host in f.listed and not official
        notes: list[str] = []
        for w in (hard or []) + (soft or []):
            if "shortener" not in w:  # the label already says it
                notes.append(T("This address {why}", why=why_text(w, reply)))
        if listed:
            notes.append(T("It is on a public list of known phishing websites"))
        if age is not None:
            notes.append(_age_note(age, T))
        elif cert is not None:
            notes.append(T("First security certificate issued {n} days ago", n=cert) if cert < 365 else T("Security certificates on record for about {n} years", n=cert // 365))
        if dns == "nxdomain":
            notes.append(T("This website address doesn't exist (any more)"))
        elif dns == "private":
            notes.append(T("It points to an internal address, which a real website never does"))
        expanded = next((d for u, d in f.shorts.items() if d and _host_of_url(u) == host), "") if host in SHORTENERS else ""
        if host in f.via:
            notes.insert(0, T("This is where the short link really goes"))
        imitated = next((m for w in (hard or []) if (m := _IMITATES.match(w))), None)

        if official:
            status, label = "official", T("The real website of {brand}", brand=official.title())
        elif listed:
            status, label = "known_phishing", T("Known phishing website")
        elif imitated:
            status, label = "lookalike", T("Looks like {official} but isn't", official=imitated.group("official"))
        elif host in SHORTENERS:
            status = "shortener"
            label = T("A short link that goes to {dest}", dest=expanded) if expanded else T("A short link: it hides where it really goes")
        elif hard or soft or (age is not None and age < 180) or dns in ("nxdomain", "private"):
            status, label = "suspicious", T("Looks suspicious")
        elif f.age_of(host) is not None and f.age_of(host) >= 730 and dns == "ok":
            status, label = "established", T("A long-established website")
        else:
            status, label = "unverified", T("Not verified")
        out.append(LinkInfo(host=host, status=status, label=label, notes=notes, expanded_to=expanded, age_days=age))
    return out
