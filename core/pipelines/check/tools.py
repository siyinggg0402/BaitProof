"""Stage 3, the tool layer behind a gate.

Every call, whoever proposed it (the deterministic planner or the model), passes the same checks:
  * the tool is in the registry and the argument really came from the message (never model-invented);
  * network tools only run when enabled, keyed where needed, inside a budget, and with a timeout;
  * we never contact the scammer's own server (no fetching their links: that would expose us and can be tracked).
    Only public registries / DNS / certificate logs / Tavily are asked *about* a domain; web text comes back as untrusted notes.
    The phishing blocklist is a local file: asking it sends nothing anywhere.
    The one tool that touches a link (expand_link) talks only to a known link SHORTENER (bit.ly and the like), reads where it redirects to, and
    stops there: the destination it names is never contacted.
Results land in `Findings`, which analysis turns into ledger evidence."""
from __future__ import annotations

import concurrent.futures as cf
import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen

from core import obs
from core.ai import verify

from . import blocklist
from .ingest import Ingested
from .knowledge import AMBIGUOUS_BRANDS, BAD_TLDS, BRANDS, LEET, OFFICIAL_ALT, SHORTENERS
from .trace import Trace

SCAM_WORDS = ("secure", "login", "verify", "account", "update", "billing", "bankmail", "support", "refund", "confirm")
IRREVERSIBLE = {"gift-card", "crypto", "wire", "safe-account"}
CARIBBEAN = {"809", "829", "849", "876", "284", "473", "649", "664", "721", "758", "767", "784", "868", "869"}  # "one-ring" scam area codes
TOLLFREE = {"800", "833", "844", "855", "866", "877", "888"}
TWO_LEVEL = {"co.uk", "org.uk", "gov.uk", "com.au", "co.nz", "co.za", "com.br", "co.in", "com.cn", "co.jp"}
PUBLIC_HOST_RE = re.compile(r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


# Wikimedia (Wikidata) throttles anonymous clients hard; its policy is to say who is asking and where to reach them. The repository is public.
USER_AGENT = os.getenv("BAITPROOF_USER_AGENT", "Baitproof/1.0 (scam-defence coach for families; https://github.com/siyinggg0402/Is-This-Legit)")


# ---------------------------------------------------------------- helpers
def _is_official(host: str, official: str) -> bool:
    return host == official or host.endswith("." + official) or (official.endswith(".gov") and host.endswith(".gov"))


def is_public_hostname(h: str) -> bool:
    return bool(PUBLIC_HOST_RE.match(h)) and not h.endswith((".local", ".internal", ".localhost", ".lan", ".home")) and h != "localhost"


# A country domain usually puts one of these between the name and the country ('dbs.com.sg', 'bbc.co.uk', 'baidu.ac.cn'): together they are the public suffix.
SECOND_LEVEL = {"com", "co", "net", "org", "gov", "edu", "ac", "or", "ne", "go", "per", "mil", "ltd", "plc", "sch", "me", "ind", "biz", "info"}


def registered_domain(host: str) -> str:
    """The part of an address that was actually registered: 'login.dbs.com.sg' -> 'dbs.com.sg', 'a.b.evil.xyz' -> 'evil.xyz'."""
    labels = host.split(".")
    if len(labels) >= 3 and (".".join(labels[-2:]) in TWO_LEVEL or (len(labels[-1]) == 2 and labels[-2] in SECOND_LEVEL)):
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _host_of_url(url: str) -> str:
    u = url.strip()
    return (urlparse(u if "//" in u else "//" + u).hostname or "").lower()


def net_enabled() -> bool:
    return os.getenv("BAITPROOF_NET_TOOLS", "1") == "1"


def _http_bytes(url: str, timeout: float = 5.0, max_bytes: int = 300_000) -> bytes:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rdap+json, application/json"})
    with urlopen(req, timeout=timeout) as r:  # noqa: S310 (fixed https registry host; argument is a validated hostname)
        return r.read(max_bytes)


def _http_json(url: str, timeout: float = 5.0, max_bytes: int = 300_000) -> dict:
    return json.loads(_http_bytes(url, timeout, max_bytes))


# ---------------------------------------------------------------- tools (each returns a small dict)
def _one_edit(a: str, b: str) -> bool:
    """True when the two words differ by exactly one letter added, dropped, changed or swapped with its neighbour (a typing slip, or a typosquat on purpose)."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        return len(diff) == 1 or (len(diff) == 2 and diff[1] == diff[0] + 1 and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])
    short, long = (a, b) if len(a) < len(b) else (b, a)
    return any(long[:i] + long[i + 1:] == short for i in range(len(long)))


# the names a typosquat imitates: each well-known brand's own name and the first label of its real addresses ('maybank2u', 'cimbclicks'), for names of six letters or more
# (a short name is one letter away from too many ordinary words), leaving out brands that are also ordinary words
_SQUAT_NAMES: dict[str, tuple[str, str]] = {}
for _brand, _site in BRANDS.items():
    if _brand in AMBIGUOUS_BRANDS:
        continue
    for _name in {_brand, _site.split(".")[0], *(a.split(".")[0] for a in OFFICIAL_ALT.get(_brand, ()))}:
        if len(_name) >= 6:
            _SQUAT_NAMES.setdefault(_name, (_brand, _site))


def _typosquat(host: str) -> tuple[str, str] | None:
    """(brand, its real address) when a word in this host is one letter away from that brand's name but the host is not the brand's own: 'maybnak2u.com.my'."""
    for token in {t for t in re.split(r"[.\-]", host) if len(t) >= 5}:
        for name, (brand, site) in _SQUAT_NAMES.items():
            if _one_edit(token, name) and not (_is_official(host, site) or any(_is_official(host, alt) for alt in OFFICIAL_ALT.get(brand, ()))):
                return brand, site
    return None


def domain_check(host: str) -> dict:
    """Deterministic lookalike analysis. 'hard' flags are near-certain (brand impersonation); 'soft' are just odd."""
    tokens = set()
    for variant in (host.translate(LEET), host.translate(LEET).replace("1", "l"), host.translate(LEET).replace("1", "i")):
        tokens |= set(re.split(r"[.\-]", variant))
        tokens.add(variant.replace("-", "").replace(".", ""))
    hard, soft, official = [], [], None
    brand = next((b for b in BRANDS if b in tokens or (b not in AMBIGUOUS_BRANDS and len(b) >= 5 and any(t.startswith(b) or t.endswith(b) for t in tokens))), None)
    if brand and not (_is_official(host, BRANDS[brand]) or any(_is_official(host, alt) for alt in OFFICIAL_ALT.get(brand, ()))):
        hard.append(f"imitates {brand} but is not {BRANDS[brand]}")
    elif brand:
        official = brand
    if not brand and (squat := _typosquat(host)):   # a one-letter slip on a known name: weak evidence by itself (real sites sometimes are), but worth saying
        soft.append(f"looks one letter away from {squat[0]} ({squat[1]})")
    if "xn--" in host:
        hard.append("uses disguised (punycode) characters")
    if re.fullmatch(r"[\d.]+", host):
        hard.append("is a raw IP address")
    if host in SHORTENERS:
        soft.append("is a link shortener that hides the real address")
    if host.endswith(BAD_TLDS):
        soft.append(f"ends in {host[host.rfind('.'):]}, common in throwaway scam sites")
    words = {w for w in re.split(r"[.\-]", host) for k in SCAM_WORDS if k in w}
    if len(words) >= 2 and not brand:
        soft.append("stacks words like 'secure' and 'login' that scam sites love")
    if host.count("-") >= 3:
        soft.append("has many hyphens")
    return {"host": host, "hard": hard, "soft": soft, "official": official}


def payment_rail(rail: str) -> dict:
    return {"rail": rail, "irreversible": rail in IRREVERSIBLE}


try:
    import phonenumbers
    from phonenumbers import PhoneNumberType as PNT
except ImportError:  # the offline phone rules are an upgrade, not a need: without the package the older prefix rules still run
    phonenumbers = None
NATIONAL_REGIONS = ("GB", "SG", "MY", "AU", "US")  # how a number written without a country code may be read (the places our users are, and the US)


def _readings(number: str) -> list[tuple[int, str, int]]:
    """Every way `number` reads as a VALID number: [(country code, national digits, type)]. A number with a '+' has one reading; one without is tried
    against the regions we serve, and a country-code-first form ('447012...') is tried with the '+' put back."""
    plus = number.startswith("+")
    digits = number.lstrip("+")
    tries = [(number, None)] if plus else [(digits, r) for r in NATIONAL_REGIONS]
    if not plus and not digits.startswith("0"):
        tries.append(("+" + digits, None))
    out: list[tuple[int, str, int]] = []
    for raw, region in tries:
        try:
            n = phonenumbers.parse(raw, region)
        except phonenumbers.NumberParseException:
            continue
        if phonenumbers.is_valid_number(n):
            out.append((n.country_code, str(n.national_number), phonenumbers.number_type(n)))
    return out


def _phone_check_prefix(number: str) -> dict:
    d = number.lstrip("+")
    npa = d[1:4] if d.startswith("1") and len(d) == 11 else (d[:3] if len(d) == 10 else "")
    kind = "unknown"
    if npa in CARIBBEAN:
        kind = "caribbean"
    elif d.startswith(("1900", "190", "449", "09", "0870", "0871", "0872", "0873")) or npa == "900":
        kind = "premium"
    elif npa in TOLLFREE:
        kind = "tollfree"
    return {"number": number, "kind": kind}


def phone_check(number: str) -> dict:
    """Local only: the number is never sent anywhere. With the `phonenumbers` package (offline rules for every country) a valid number is classified:
    'caribbean' (area codes tied to 'one-ring' scams), 'premium' (a premium-rate number that can charge heavily), 'personal' (UK 070 "personal numbers",
    which scammers use to look like a mobile), 'tollfree', or 'unknown'. A number written without a country code that could be read two ways is only
    called premium or personal if every valid reading says so. The older prefix rules still run as well and only ever ADD a finding: scam messages are
    sloppy (a 12-digit '0871...' is not a valid number, but it is still an 0871 number), and measured on 1,019 real scam texts, dropping them lost 13 catches."""
    old = _phone_check_prefix(number)
    if phonenumbers is None:
        return old
    reads = _readings(number)
    types = {t for _, _, t in reads}
    kind = "unknown"
    if any(cc == 1 and nat[:3] in CARIBBEAN for cc, nat, _ in reads):
        kind = "caribbean"
    elif types == {PNT.PREMIUM_RATE}:
        kind = "premium"
    elif types == {PNT.PERSONAL_NUMBER}:
        kind = "personal"
    elif old["kind"] in ("caribbean", "premium"):
        kind = old["kind"]
    elif PNT.TOLL_FREE in types or old["kind"] == "tollfree":
        kind = "tollfree"
    return {"number": number, "kind": kind}


def domain_age(host: str) -> dict:
    """How long ago the registered domain was created, from the public RDAP registry (not from the site itself)."""
    dom = registered_domain(host)
    data = _http_json("https://rdap.org/domain/" + quote(dom))
    reg = next((e.get("eventDate") for e in data.get("events", []) if e.get("eventAction") == "registration"), None)
    if not reg:
        return {"host": host, "domain": dom, "age_days": None}
    created = datetime.fromisoformat(reg.replace("Z", "+00:00"))
    return {"host": host, "domain": dom, "age_days": max(0, (datetime.now(timezone.utc) - created).days)}


FAKE_IP_NETS = [ipaddress.ip_network("198.18.0.0/15"), ipaddress.ip_network("100.64.0.0/10")]  # proxy "fake-ip" and carrier-grade NAT ranges
_resolver_cache: dict = {"ok": None, "at": 0.0}


def _internal(ip: str) -> bool:
    a = ipaddress.ip_address(ip.split("%")[0])
    return a.is_private or a.is_loopback or a.is_link_local


def _fake(ip: str) -> bool:
    a = ipaddress.ip_address(ip.split("%")[0])
    return any(a in n for n in FAKE_IP_NETS)


def resolver_trustworthy() -> bool:
    """Self-calibration: a resolver that rewrites answers (VPN/proxy fake-IP mode, ISP wildcard pages) makes DNS evidence worse than
    useless. Check a known-good name and a guaranteed-missing one; cache the verdict for 10 minutes."""
    import secrets as _s

    now = time.time()
    if _resolver_cache["ok"] is not None and now - _resolver_cache["at"] < 600:
        return _resolver_cache["ok"]
    ok = True
    try:
        ips = {i[4][0] for i in socket.getaddrinfo("example.com", None)}
        ok = not any(_internal(ip) or _fake(ip) for ip in ips)  # a real public site must not resolve to a private/fake address
    except OSError:
        ok = False  # cannot resolve a known-good domain: our network is the problem, not the site we're asked about
    if ok:
        try:
            socket.getaddrinfo(f"bp-nx-{_s.token_hex(8)}.com", None)
            ok = False  # a name that cannot exist resolved: the resolver invents answers
        except socket.gaierror:
            pass
        except OSError:
            ok = False
    _resolver_cache.update(ok=ok, at=now)
    return ok


def dns_check(host: str) -> dict:
    """Does the name exist, and does it point somewhere internal? A DNS question, not a visit to the site.
    Reports 'unreliable' (and so adds no evidence) when the local resolver can't be trusted."""
    if not resolver_trustworthy():
        return {"host": host, "status": "unreliable"}
    try:
        ips = {i[4][0] for i in socket.getaddrinfo(host, None)}
    except socket.gaierror:
        return {"host": host, "status": "nxdomain"}
    return {"host": host, "status": "private" if any(_internal(ip) for ip in ips) else "ok"}


ORG_CLAIMS = {"P159", "P452", "P1128", "P2139", "P355", "P749", "P112", "P1454", "P169"}  # Wikidata: headquarters, industry, employees, revenue, subsidiary, parent, founder, legal form, CEO
GENERIC_ORGS = {"bank", "your bank", "the bank", "support", "support team", "customer service", "your provider", "service", "team", "office", "company", "your account"}


def official_site_wikidata(org: str) -> dict:
    """Free, keyless: ask Wikidata (community-maintained, public) what the organisation's OFFICIAL WEBSITE is (property P856).
    Only the organisation name from the message is sent; we never visit any website."""
    hit_label, hosts, exists = None, [], False
    found = _http_json("https://www.wikidata.org/w/api.php?action=wbsearchentities&language=en&format=json&limit=3&type=item&search=" + quote(org))
    words = {w for w in re.findall(r"[a-z0-9]{3,}", org.lower())}
    for hit in found.get("search", [])[:3]:
        label = str(hit.get("label", "")).lower()
        if words and not (words & set(re.findall(r"[a-z0-9]{3,}", label))):
            continue  # the top hit must actually be about this name
        qid = hit.get("id", "")
        if not re.fullmatch(r"Q\d+", qid):
            continue
        ent = _http_json(f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json")
        claims = ent.get("entities", {}).get(qid, {}).get("claims", {})
        for claim in claims.get("P856", []):
            url = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            if isinstance(url, str):
                h = re.sub(r"^www\.", "", (urlparse(url).hostname or "").lower())
                if h:
                    hosts.append(h)
        if hosts or ORG_CLAIMS & set(claims):  # a website, or facts only an organisation has (headquarters, industry, employees, revenue, parent...)
            hit_label = hit.get("label")
            exists = True
            break
    return {"org": org, "hosts": list(dict.fromkeys(hosts)), "label": hit_label, "exists": exists}


def brand_lookup(org: str) -> dict:
    return {"org": org, "hosts": verify.official_sites(org)}


def reputation(host: str) -> dict:
    return {"host": host, "notes": verify.enrich([host], limit=1)}


def blocklist_check(host: str) -> dict:
    """Is this address on a public list of known phishing sites? Answered from a local copy of the list (see blocklist.py): the address is not sent anywhere.
    The exact name is looked up, and so is its registered domain (so a throwaway subdomain of a listed site is caught), except on sites where anyone can host
    a page, where only the exact name counts. A link shortener (the real list carries bit.ly and a few others, because phishers use them) and an open
    hosting platform are never judged by the list: the shortener's destination is looked up once it is known. status: listed | clean | exempt | unavailable
    (no list on this machine yet)."""
    if not blocklist.available():
        return {"host": host, "status": "unavailable", "listed": ""}
    if host in SHORTENERS or blocklist.exempt(host):
        return {"host": host, "status": "exempt", "listed": ""}
    names = [host]
    reg = registered_domain(host)
    if reg != host and reg not in blocklist.SHARED_HOSTING:
        names.append(reg)
    hit = blocklist.lookup(names)
    return {"host": host, "status": "listed" if hit else "clean", "listed": hit}


CERT_TIMEOUT = 8.0
CERT_MAX_BYTES = 500_000
CERT_CACHE_SECONDS = 24 * 3600  # a domain's first certificate does not change
CERT_CACHE_MAX = 512
CERT_PAUSE_SECONDS = 300  # crt.sh is a free service that often answers "too many requests" or times out: after a failure, leave it alone for a while
_cert_cache: dict[str, tuple[float, dict]] = {}
_cert_pause = {"until": 0.0}


def cert_history(host: str) -> dict:
    """When did a security (HTTPS) certificate first appear for this website's registered domain? Certificate Transparency logs are public by design and
    searchable through crt.sh (free, no key): they are the record of every certificate issued, so they show when a site started being run, even where the
    domain registry (RDAP) says nothing. Only the domain name is sent, and only to crt.sh. A domain with very many certificates (an established site)
    overflows the size cap: that is reported as `many`, and `first_days` is then unknown rather than guessed."""
    dom = registered_domain(host)
    now = time.time()
    if (hit := _cert_cache.get(dom)) and now - hit[0] < CERT_CACHE_SECONDS:
        return {**hit[1], "host": host}
    if now < _cert_pause["until"]:
        raise RuntimeError("the certificate log is being left alone for a few minutes after an error")
    try:
        raw = _http_bytes("https://crt.sh/?output=json&q=" + quote(dom), timeout=CERT_TIMEOUT, max_bytes=CERT_MAX_BYTES)
    except OSError:  # a timeout, an HTTP error such as 429 Too Many Requests, a refused connection
        _cert_pause["until"] = now + CERT_PAUSE_SECONDS
        raise
    text = raw.decode("utf-8", "replace")
    dates = re.findall(r'"not_before"\s*:\s*"(\d{4}-\d{2}-\d{2})', text)
    if not dates and text.strip() not in ("", "[]"):
        raise ValueError("unexpected answer from the certificate log")
    many = len(raw) >= CERT_MAX_BYTES
    first_days = None
    if dates and not many:  # a cut-off answer may hide the earliest certificate, so no age is claimed from it
        first = datetime.fromisoformat(min(dates)).replace(tzinfo=timezone.utc)
        first_days = max(0, (datetime.now(timezone.utc) - first).days)
    out = {"host": host, "domain": dom, "certs": len(dates), "first_days": first_days, "many": many}
    if len(_cert_cache) >= CERT_CACHE_MAX:
        _cert_cache.pop(next(iter(_cert_cache)))
    _cert_cache[dom] = (now, out)
    return out


# -- domain_owner: who registered this address?
WHOIS_TIMEOUT = 6.0
WHOIS_MAX_BYTES = 30_000
_whois_servers: dict[str, str] = {}  # top-level domain -> the registry's WHOIS server ('' = it has none)
_REDACTED = re.compile(r"redact|privacy|protect|withheld|not disclosed|not available|proxy|whoisguard|data protected|gdpr|anonym|masked|statutory|n/a", re.I)
_EMAIL_DOMAIN = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
_OWNER_NAME = re.compile(r"[^\w .,&()'/-]+", re.UNICODE)


def _whois_address(server: str) -> str:
    """The address of a WHOIS server. Every address must be public; the one exception is the 'fake-ip' block (198.18.0.0/15) that VPN and proxy software hands out
    for every name, which is a tunnel to the real server rather than a door into this network. The server's name comes from the IANA list, not from the message."""
    ips = [i[4][0] for i in socket.getaddrinfo(server, 43, type=socket.SOCK_STREAM)]
    if not ips or not all(public_address(ip) or _fake(ip) for ip in ips):
        raise ValueError("refused: the WHOIS server does not resolve to a public address")
    return ips[0]


def _whois_raw(server: str, query: str, timeout: float) -> str:
    """One WHOIS question (port 43) to a registry's server, which is looked up on the IANA list and must be a public host. The query is the domain name only."""
    if not re.fullmatch(r"[a-z0-9.-]{3,253}", server):
        raise ValueError("odd WHOIS server name")
    ip = _whois_address(server)
    with socket.create_connection((ip, 43), timeout) as s:
        s.settimeout(timeout)
        s.sendall((query + "\r\n").encode("ascii", "ignore"))
        out = b""
        while len(out) < WHOIS_MAX_BYTES:
            try:
                chunk = s.recv(4096)
            except (socket.timeout, OSError):
                break
            if not chunk:
                break
            out += chunk
    return out.decode("utf-8", "replace")


def _whois_server(tld: str) -> str:
    if tld not in _whois_servers:
        text = _whois_raw("whois.iana.org", tld, WHOIS_TIMEOUT)
        _whois_servers[tld] = next((m.group(1).strip().lower() for l in text.splitlines() if (m := re.match(r"whois:\s*(\S+)", l, re.I))), "")
    return _whois_servers[tld]


def _owner_text(v: str) -> str:
    """The registrant's name as the registry printed it: it is written by whoever registered the domain, so only plain name characters survive."""
    return " ".join(_OWNER_NAME.sub(" ", v).split())[:80]


def parse_whois(text: str) -> dict:
    """{registrant, email_domains, registrar, status}. Redacted ('REDACTED FOR PRIVACY') values are ignored. status: found | redacted | empty."""
    registrant, registrar, emails, redacted = "", "", [], False
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key, val = key.strip().lower(), val.strip()
        if not val:
            continue
        if _REDACTED.search(val):
            redacted = True
            continue
        if key in ("registrant organization", "registrant organisation", "registrant", "registrant name", "organization", "org") and not registrant:
            registrant = _owner_text(val)
        elif key in ("registrar", "sponsoring registrar") and not registrar:
            registrar = _owner_text(val)
        elif ("email" in key or "e-mail" in key) and key.split()[0] in ("registrant", "tech", "admin", "email", "technical", "administrative"):
            for m in _EMAIL_DOMAIN.finditer(val):
                d = m.group(1).lower()
                if d not in emails and len(emails) < 4:
                    emails.append(d)
    return {"registrant": registrant, "email_domains": emails, "registrar": registrar, "status": "found" if registrant or emails else ("redacted" if redacted else "empty")}


def domain_owner(host: str) -> dict:
    """Who registered this address, from the registry's public WHOIS record (not from the site). Country registries such as .cn, .sg, .my and .hk
    publish the registrant and a contact address; many .com records are redacted. Only the domain name is sent, and only to the registry."""
    dom = registered_domain(host)
    server = _whois_server(dom.rsplit(".", 1)[-1])
    if not server:
        return {"host": host, "domain": dom, "registrant": "", "email_domains": [], "registrar": "", "status": "unavailable"}
    return {"host": host, "domain": dom, **parse_whois(_whois_raw(server, dom, WHOIS_TIMEOUT))}


# -- expand_link: where does a short link really go?
MAX_HOPS = 3  # at most this many requests, and only to shorteners
HOP_TIMEOUT = 3.0  # seconds for one request (connect + answer)
EXPAND_DEADLINE = 7.0  # seconds for the whole tool
REDIRECTS = (301, 302, 303, 307, 308)
_BAD_ADDR_NETS = [ipaddress.ip_network(n) for n in ("0.0.0.0/8", "100.64.0.0/10", "198.18.0.0/15", "192.0.0.0/24", "240.0.0.0/4", "fc00::/7", "fe80::/10", "64:ff9b::/96")]


def public_address(ip: str) -> bool:
    """True only for an address on the open internet. Private, loopback, link-local, carrier-grade NAT, proxy 'fake-ip', multicast, reserved and
    unspecified addresses (and IPv6 forms that wrap one of them) are all refused: a short link must never be a way to make this server knock on a door
    inside its own network (SSRF)."""
    try:
        a = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    if isinstance(a, ipaddress.IPv6Address) and a.ipv4_mapped:
        a = a.ipv4_mapped
    return bool(a.is_global and not (a.is_private or a.is_loopback or a.is_link_local or a.is_multicast or a.is_reserved or a.is_unspecified) and not any(a in n for n in _BAD_ADDR_NETS))


def _resolve_public(host: str, port: int = 443) -> str:
    """The address to connect to for `host`, refusing the name unless EVERY address it resolves to is public. We then connect to that address
    itself, so the name cannot resolve to something else a moment later (DNS rebinding)."""
    ips = [i[4][0] for i in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)]
    if not ips or not all(public_address(ip) for ip in ips):
        raise ValueError("refused: the name does not resolve to a public address")
    return ips[0]


class _PinnedHTTPS(http.client.HTTPSConnection):
    """HTTPS to a chosen IP address, with the certificate still checked against the host name."""

    def __init__(self, host: str, ip: str, timeout: float) -> None:
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self._ip = ip

    def connect(self) -> None:
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def _head(host: str, ip: str, target: str, timeout: float) -> tuple[int, str]:
    """One HEAD request, redirects NOT followed. Returns (status, Location header). Nothing of the body is read."""
    conn = _PinnedHTTPS(host, ip, timeout)
    try:
        conn.request("HEAD", target, headers={"User-Agent": "Baitproof/1.0 (scam-defense; reads where a short link goes)", "Accept": "*/*", "Connection": "close"})
        r = conn.getresponse()
        return r.status, (r.getheader("Location") or "")[:2048]
    finally:
        conn.close()


def _short_url(url: str) -> tuple[str, str] | None:
    """(host, request target) of a short link as we will ask for it (always https), or None when it is not a shortener link."""
    u = url.strip()
    parts = urlparse(u if "//" in u else "//" + u)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("", "http", "https") or host not in SHORTENERS or not is_public_hostname(host):
        return None
    target = (parts.path or "/") + (("?" + parts.query) if parts.query else "")
    return host, target[:512]


def expand_link(url: str) -> dict:
    """Where does a SHORT link go? Ask the shortener (a HEAD request over https, redirects not followed) and read only the Location header; follow at most
    three hops, and only while the next stop is another shortener. The destination is only NAMED, never contacted. Returns
    {"url", "host", "dest": host it goes to ('' if we could not tell), "hops", "status": expanded | no_redirect | too_many_hops | refused}."""
    t_end = time.monotonic() + EXPAND_DEADLINE
    first = _short_url(url)
    if first is None:
        return {"url": url, "host": "", "dest": "", "hops": 0, "status": "refused"}
    host, target = first
    hops = 0
    while hops < MAX_HOPS:
        left = t_end - time.monotonic()
        if left <= 0.2:
            raise TimeoutError("expand_link deadline")
        ip = _resolve_public(host)
        hops += 1
        status, loc = _head(host, ip, target, min(HOP_TIMEOUT, left))
        if status not in REDIRECTS or not loc:
            return {"url": url, "host": first[0], "dest": "", "hops": hops, "status": "no_redirect"}
        nxt = urlparse(urljoin(f"https://{host}{target}", loc.strip()))
        if nxt.scheme not in ("http", "https") or not nxt.hostname:
            return {"url": url, "host": first[0], "dest": "", "hops": hops, "status": "no_redirect"}
        try:
            nhost = nxt.hostname.lower().rstrip(".").encode("idna").decode("ascii")  # a non-Latin name becomes its xn-- form, which domain_check flags
        except UnicodeError:
            return {"url": url, "host": first[0], "dest": "", "hops": hops, "status": "no_redirect"}
        if not re.fullmatch(r"[a-z0-9._-]{1,253}", nhost):  # the scammer wrote this header: only something shaped like a host name goes any further (it ends up in the findings)
            return {"url": url, "host": first[0], "dest": "", "hops": hops, "status": "no_redirect"}
        if nhost in SHORTENERS and is_public_hostname(nhost):
            host, target = nhost, ((nxt.path or "/") + (("?" + nxt.query) if nxt.query else ""))[:512]
            continue
        return {"url": url, "host": first[0], "dest": nhost, "hops": hops, "status": "expanded"}  # the host only: its path may carry the scammer's tracking id
    return {"url": url, "host": first[0], "dest": "", "hops": hops, "status": "too_many_hops"}


@dataclass(frozen=True)
class Spec:
    name: str
    arg: str  # what kind of argument: host | rail | phone | org | url
    fn: Callable[[str], dict]
    desc: str  # shown to the model planner
    net: bool = False
    timeout: float = 5.0
    requires: str = ""  # env var that must be set


SPECS: dict[str, Spec] = {s.name: s for s in [
    Spec("domain_check", "host", domain_check, "Check a link's address for brand imitation, odd endings, shorteners (local, free)."),
    Spec("payment_rail", "rail", payment_rail, "Is the requested payment method one that can't be reversed (local, free)."),
    Spec("phone_check", "phone", phone_check, "Is a phone number's area code linked to one-ring / premium-rate scams (local, free)."),
    Spec("domain_age", "host", domain_age, "How long ago the website address was registered, via the public registry. New sites are a scam sign.", net=True, timeout=6),
    Spec("dns_check", "host", dns_check, "Does the website address exist, and does it point somewhere internal.", net=True, timeout=4),
    Spec("official_site_wikidata", "org", official_site_wikidata, "Ask Wikidata (free, public) for the real company's official website, to compare with the link in the message.", net=True, timeout=8),
    Spec("brand_lookup", "org", brand_lookup, "Search the web for the real website of the company the message claims to be.", net=True, timeout=10, requires="TAVILY_API_KEY"),
    Spec("reputation", "host", reputation, "Search the web for scam reports about this website.", net=True, timeout=10, requires="TAVILY_API_KEY"),
    Spec("blocklist_check", "host", blocklist_check, "Is this website address on a public list of known phishing sites (checked on this machine; nothing is sent)."),
    Spec("cert_history", "host", cert_history, "When the website first got a security certificate, from public Certificate Transparency logs. Use when the registry could not say how old the site is.", net=True, timeout=10),
    Spec("domain_owner", "host", domain_owner, "Who registered the website address, from the registry record. Compare with the real company's website.", net=True, timeout=14),
    Spec("expand_link", "url", expand_link, "Find out where a SHORT link (bit.ly and the like) really goes, by asking the shortener where it redirects. The destination is never visited.", net=True, timeout=9),
]}


# ---------------------------------------------------------------- findings
@dataclass
class Findings:
    hosts: list[str] = field(default_factory=list)
    hard_hosts: dict[str, list[str]] = field(default_factory=dict)
    soft_hosts: dict[str, list[str]] = field(default_factory=dict)
    official_hosts: dict[str, str] = field(default_factory=dict)  # host -> brand whose real site it is
    irreversible_rails: list[str] = field(default_factory=list)
    phones: dict[str, str] = field(default_factory=dict)  # number -> kind
    ages: dict[str, int | None] = field(default_factory=dict)  # host -> registration age in days
    dns: dict[str, str] = field(default_factory=dict)  # host -> ok | nxdomain | private
    listed: dict[str, str] = field(default_factory=dict)  # host -> the entry on the public phishing list that matched it
    owners: dict[str, dict] = field(default_factory=dict)  # host -> {"registrant": name, "emails": [domains of the registrant's contact addresses]}
    orgs_real: dict[str, str] = field(default_factory=dict)  # organisation as named -> its name on Wikidata (it exists, whatever the message says)
    certs: dict[str, int | None] = field(default_factory=dict)  # host -> days since its domain's first logged security certificate (None = could not tell)
    brand_sites: dict[str, list[str]] = field(default_factory=dict)  # org -> hostnames the web says are official
    brand_src: dict[str, str] = field(default_factory=dict)  # org -> 'wikidata' | 'web search'
    web_notes: list[str] = field(default_factory=list)  # UNTRUSTED: shown as neutral notes, never weighed
    shorts: dict[str, str] = field(default_factory=dict)  # short link as written -> the host it really goes to ('' while unknown)
    via: dict[str, str] = field(default_factory=dict)  # destination host -> the short link (as written in the message) that leads there
    done: set = field(default_factory=set)  # (tool, arg) already answered

    @property
    def suspicious_hosts(self) -> list[str]:
        return list(dict.fromkeys([*self.hard_hosts, *self.soft_hosts, *self.listed]))

    def resolved_shorteners(self) -> set[str]:
        """Short-link hosts whose every link in the message we have followed to its destination: those hosts stand aside for where they lead."""
        out = set()
        for h in self.hosts:
            urls = [u for u in self.shorts if _host_of_url(u) == h]
            if h in SHORTENERS and urls and all(self.shorts[u] for u in urls):
                out.add(h)
        return out

    def _judged_hosts(self) -> list[str]:
        gone = self.resolved_shorteners()
        return [h for h in self.hosts if h not in gone]

    def age_of(self, host: str) -> int | None:
        """How old the site is, in days. The domain registry is the authority when it answered; otherwise the first logged certificate, which is a floor
        (the domain is at least that old) and nothing more, because a domain can exist long before it first gets a certificate."""
        a = self.ages.get(host)
        return a if a is not None else self.certs.get(host)

    def owned_by(self, host: str) -> str:
        """The company that itself registered this address: the registry's contact address for it is on that company's own website (one we know from Wikidata,
        the web, or the brand table). '' when we cannot tell. The record is written by whoever registered the domain, so this is supporting evidence, never proof."""
        o = self.owners.get(host)
        if not o or not o.get("emails"):
            return ""
        mine = {registered_domain(d) for d in o["emails"]}
        for org, sites in self.brand_sites.items():
            if mine & {registered_domain(s) for s in sites}:
                return org
        return next((b for b, dom in BRANDS.items() if registered_domain(dom) in mine), "")

    def all_links_official(self) -> bool:
        hs = self._judged_hosts()
        return bool(hs) and all(h in self.official_hosts or self.owned_by(h) for h in hs)

    def all_links_established(self) -> bool:
        """Every link is either a known real site, or an old, resolving domain (2+ years): a link we have positive reason to trust.
        A short link's own age says nothing about where it goes, so it only counts once it has been followed to its destination."""
        hs = self._judged_hosts()
        return bool(hs) and all(h in self.official_hosts or self.owned_by(h) or (h not in SHORTENERS and (self.age_of(h) or 0) >= 730 and self.dns.get(h) == "ok" and h not in self.listed) for h in hs)

    def apply(self, tool: str, arg: str, d: dict) -> None:
        self.done.add((tool, arg))
        if tool == "domain_check":
            if d["hard"]:
                self.hard_hosts[arg] = d["hard"]
            elif d["soft"]:
                self.soft_hosts[arg] = d["soft"]
            if d.get("official"):
                self.official_hosts[arg] = d["official"]
        elif tool == "payment_rail" and d["irreversible"]:
            self.irreversible_rails.append(arg)
        elif tool == "phone_check":
            self.phones[arg] = d["kind"]
        elif tool == "domain_age":
            self.ages[arg] = d["age_days"]
        elif tool == "dns_check":
            self.dns[arg] = d["status"]
        elif tool == "blocklist_check":
            if d.get("listed"):
                self.listed[arg] = d["listed"]
        elif tool == "cert_history":
            self.certs[arg] = d.get("first_days")
        elif tool == "domain_owner":
            if d.get("status") == "found":
                self.owners[arg] = {"registrant": d.get("registrant", ""), "emails": d.get("email_domains", [])}
        elif tool in ("brand_lookup", "official_site_wikidata"):
            if d["hosts"] or arg not in self.brand_sites:  # never let an empty answer overwrite a real one
                self.brand_sites[arg] = d["hosts"]
                self.brand_src[arg] = "wikidata" if tool == "official_site_wikidata" else "web search"
            if d.get("exists") or d["hosts"]:
                self.orgs_real[arg] = d.get("label") or arg
        elif tool == "reputation":
            self.web_notes += d["notes"]
        elif tool == "expand_link":
            dest = d.get("dest", "")
            self.shorts.setdefault(arg, "")
            if dest:
                self.shorts[arg] = dest
                self.via.setdefault(dest, arg)
                if dest not in self.hosts:
                    self.hosts.append(dest)
                short = _host_of_url(arg)
                if short in self.resolved_shorteners() and short in self.soft_hosts:  # it no longer hides anything
                    left = [w for w in self.soft_hosts[short] if "shortener" not in w]
                    if left:
                        self.soft_hosts[short] = left
                    else:
                        del self.soft_hosts[short]

    def summary(self) -> str:
        parts = [f"the short link {_host_of_url(u)} really goes to {d}" for u, d in self.shorts.items() if d]
        parts += [f"{h}: {'; '.join(v)}" for h, v in {**self.soft_hosts, **self.hard_hosts}.items()]
        parts += [f"{h} is the real website of {b}" for h, b in self.official_hosts.items()]
        parts += [f"payment method '{r}' cannot be reversed" for r in self.irreversible_rails]
        parts += [f"{h} was registered {a} days ago" for h, a in self.ages.items() if a is not None]
        parts += [f"{h} does not resolve" for h, s in self.dns.items() if s == "nxdomain"]
        parts += [f"{h} is on a public list of known phishing websites" for h in self.listed]
        parts += [f"{h} is registered by {self.owned_by(h).title()} itself (the registry's contact address is on {self.owned_by(h).title()}'s own website)" for h in self.owners if self.owned_by(h)]
        parts += [f"{o.title()} is a real, known organisation (Wikidata)" for o in self.orgs_real]
        parts += [f"{h} first got a security certificate {c} days ago" for h, c in self.certs.items() if c is not None and self.ages.get(h) is None]
        parts += [f"phone {p} looks like a {k} number" for p, k in self.phones.items() if k in ("caribbean", "premium", "personal")]
        parts += [f"{self.brand_src.get(o, 'the web')} lists {', '.join(h[:3])} as {o}'s official site" for o, h in self.brand_sites.items() if h]
        return "\n".join(parts) or "no deterministic findings"


# ---------------------------------------------------------------- the gate
_POOL = cf.ThreadPoolExecutor(max_workers=6, thread_name_prefix="bp-tool")


class ToolGate:
    def __init__(self, ing: Ingested, claimed_org: str, trace: Trace, budget: int = 6) -> None:
        self.ing, self.org, self.trace, self.budget, self.used = ing, (claimed_org or "").lower(), trace, budget, 0
        self.blocked: list[str] = []
        self.derived: set[str] = set()  # hosts learned from a short link in the message (via expand_link): not written in the message, but it leads there

    # -- validation ----------------------------------------------------------------------------------------------
    def _arg_ok(self, spec: Spec, arg: str) -> bool:
        e = self.ing.entities
        if spec.arg == "host":
            return (arg in e.hosts or arg in self.derived) and (not spec.net or is_public_hostname(arg))
        if spec.arg == "url":
            return arg in e.urls and _short_url(arg) is not None  # a link written in the message, and one on the shortener list
        if spec.arg == "rail":
            return arg in e.rails
        if spec.arg == "phone":
            return arg in e.phones
        if spec.arg == "org":
            if not arg or arg.lower() in GENERIC_ORGS:
                return False
            if arg.lower() in {n.lower() for n in (self.ing.origin.names() if self.ing.origin else [])}:
                return True  # the app or brand a screenshot showed: not written in the text, but it is where the message came from
            return arg.lower() in ({self.org} | set(e.brands)) and arg.lower() in self.ing.text.lower()
        return False

    def available(self, name: str, arg: str, done: set) -> bool:
        """Quiet pre-check used by the planner so it never proposes calls the gate would refuse."""
        spec = SPECS.get(name)
        return bool(spec and (name, arg) not in done and self._arg_ok(spec, arg) and (not spec.requires or os.getenv(spec.requires))
                    and (not spec.net or (net_enabled() and self.used < self.budget)))

    def _refuse(self, status: str, msg: str) -> None:
        self.blocked.append(msg)
        self.trace.add("tools", status, msg)

    def check(self, name: str, arg: str, done: set) -> Spec | None:
        """None = refused (and traced). Duplicates are silently skipped (None, untraced)."""
        spec = SPECS.get(name)
        if spec is None:
            self._refuse("block", f"unknown tool '{name}' refused")
        elif (name, arg) in done:
            return None
        elif not self._arg_ok(spec, arg):
            self._refuse("block", f"{name}: argument was not found in the message")
        elif spec.requires and not os.getenv(spec.requires):
            self.blocked.append(f"{name}: needs {spec.requires}")  # expected in offline mode: quiet, not an alarm
        elif spec.net and not net_enabled():
            self.blocked.append(f"{name}: network tools are off")
        elif spec.net and self.used >= self.budget:
            self._refuse("block", f"{name}: tool budget ({self.budget}) used up")
        else:
            return spec
        return None

    # -- execution -----------------------------------------------------------------------------------------------
    def run(self, calls: list[tuple[str, str]], f: Findings) -> int:
        """Validate every call first, then run local ones inline and network ones in parallel. Returns how many ran."""
        ready: list[tuple[Spec, str]] = []
        for name, arg in calls:
            spec = self.check(name, arg, f.done)
            if spec and (spec, arg) not in ready:
                if spec.net:
                    self.used += 1
                ready.append((spec, arg))
        futures = {}
        for spec, arg in ready:
            if spec.net:
                futures[(spec.name, arg)] = (spec, time.perf_counter(), _POOL.submit(spec.fn, arg))
            else:
                self._finish(spec, arg, time.perf_counter(), lambda s=spec, a=arg: s.fn(a), f)
        for (name, arg), (spec, t0, fut) in futures.items():
            self._finish(spec, arg, t0, lambda fu=fut, sp=spec: fu.result(timeout=sp.timeout), f)
        return len(ready)

    def _finish(self, spec: Spec, arg: str, t0: float, get: Callable[[], dict], f: Findings) -> None:
        try:
            data = get()
            f.apply(spec.name, arg, data)
            if spec.name == "expand_link" and data.get("dest"):
                self._learn(data["dest"], f)
            obs.record_tool(tool=spec.name, ok=True, ms=int((time.perf_counter() - t0) * 1000))
        except Exception as e:  # timeout, network, parse: a failed tool is a missing fact, never a crash
            f.done.add((spec.name, arg))
            obs.record_tool(tool=spec.name, ok=False, ms=int((time.perf_counter() - t0) * 1000), error=type(e).__name__)
            self.trace.add("tools", "skip", f"{spec.name} unavailable ({type(e).__name__}); continuing without it")

    def _learn(self, host: str, f: Findings) -> None:
        """A short link led somewhere: that host may now be asked about like any link in the message, and the free local check runs at once."""
        self.derived.add(host)
        if ("domain_check", host) not in f.done:
            f.apply("domain_check", host, domain_check(host))
        if ("blocklist_check", host) not in f.done:
            f.apply("blocklist_check", host, blocklist_check(host))


def initial_calls(ing: Ingested) -> list[tuple[str, str]]:
    """Round 0: the local, free checks, plus finding out where a SHORT link goes. That one is a network call, but it is asked first because the answer decides
    what the link IS (a short link says nothing about itself); the gate still holds it to the allow-list, the budget, the timeout and the offline switch."""
    e = ing.entities
    shorts = [("expand_link", u) for u in e.urls if _host_of_url(u) in SHORTENERS][:2]
    return ([("domain_check", h) for h in e.hosts[:3]] + [("blocklist_check", h) for h in e.hosts[:3]] + [("payment_rail", r) for r in e.rails] + [("phone_check", p) for p in e.phones[:2]] + shorts)


def run_tools(ing: Ingested, trace: Trace, claimed_org: str = "") -> tuple[Findings, ToolGate]:
    """Round 0 of the tool layer. Returns the findings and the gate (the loop reuses it for later rounds)."""
    f = Findings(hosts=list(ing.entities.hosts[:3]))
    f.shorts = {u: "" for u in ing.entities.urls if _host_of_url(u) in SHORTENERS}
    gate = ToolGate(ing, claimed_org, trace)
    n = gate.run(initial_calls(ing), f)
    trace.add("tools", "flag" if f.suspicious_hosts or f.irreversible_rails else "pass", f"{n} {'check(s)' if f.shorts else 'local check(s)'}; " + f.summary().replace("\n", " | "))
    return f, gate
