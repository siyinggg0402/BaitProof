"""Stage 3, the tool layer behind a gate.

Every call, whoever proposed it (the deterministic planner or the model), passes the same checks:
  * the tool is in the registry and the argument really came from the message (never model-invented);
  * network tools only run when enabled, keyed where needed, inside a budget, and with a timeout;
  * we never contact the scammer's own server (no fetching their links: that would expose us and can be tracked).
    Only public registries / DNS / Tavily are asked *about* a domain; web text comes back as untrusted notes.
Results land in `Findings`, which analysis turns into ledger evidence."""
from __future__ import annotations

import concurrent.futures as cf
import ipaddress
import json
import os
import re
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable
from urllib.parse import quote
from urllib.request import Request, urlopen

from core import obs
from core.ai import verify

from .ingest import Ingested
from .knowledge import AMBIGUOUS_BRANDS, BAD_TLDS, BRANDS, LEET, SHORTENERS
from .trace import Trace

SCAM_WORDS = ("secure", "login", "verify", "account", "update", "billing", "bankmail", "support", "refund", "confirm")
IRREVERSIBLE = {"gift-card", "crypto", "wire", "safe-account"}
CARIBBEAN = {"809", "829", "849", "876", "284", "473", "649", "664", "721", "758", "767", "784", "868", "869"}  # "one-ring" scam area codes
TOLLFREE = {"800", "833", "844", "855", "866", "877", "888"}
TWO_LEVEL = {"co.uk", "org.uk", "gov.uk", "com.au", "co.nz", "co.za", "com.br", "co.in", "com.cn", "co.jp"}
PUBLIC_HOST_RE = re.compile(r"^(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


# ---------------------------------------------------------------- helpers
def _is_official(host: str, official: str) -> bool:
    return host == official or host.endswith("." + official) or (official.endswith(".gov") and host.endswith(".gov"))


def is_public_hostname(h: str) -> bool:
    return bool(PUBLIC_HOST_RE.match(h)) and not h.endswith((".local", ".internal", ".localhost", ".lan", ".home")) and h != "localhost"


def registered_domain(host: str) -> str:
    labels = host.split(".")
    if len(labels) >= 3 and ".".join(labels[-2:]) in TWO_LEVEL:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def net_enabled() -> bool:
    return os.getenv("BAITPROOF_NET_TOOLS", "1") == "1"


def _http_json(url: str, timeout: float = 5.0, max_bytes: int = 300_000) -> dict:
    req = Request(url, headers={"User-Agent": "Baitproof/1.0 (scam-defense; +https://github.com)", "Accept": "application/rdap+json, application/json"})
    with urlopen(req, timeout=timeout) as r:  # noqa: S310 (fixed https registry host; argument is a validated hostname)
        return json.loads(r.read(max_bytes))


# ---------------------------------------------------------------- tools (each returns a small dict)
def domain_check(host: str) -> dict:
    """Deterministic lookalike analysis. 'hard' flags are near-certain (brand impersonation); 'soft' are just odd."""
    tokens = set()
    for variant in (host.translate(LEET), host.translate(LEET).replace("1", "l"), host.translate(LEET).replace("1", "i")):
        tokens |= set(re.split(r"[.\-]", variant))
        tokens.add(variant.replace("-", "").replace(".", ""))
    hard, soft, official = [], [], None
    brand = next((b for b in BRANDS if b in tokens or (b not in AMBIGUOUS_BRANDS and len(b) >= 5 and any(t.startswith(b) or t.endswith(b) for t in tokens))), None)
    if brand and not _is_official(host, BRANDS[brand]):
        hard.append(f"imitates {brand} but is not {BRANDS[brand]}")
    elif brand:
        official = brand
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


def phone_check(number: str) -> dict:
    """Local only: the number is never sent anywhere. Flags area codes tied to 'one-ring' and premium-rate scams."""
    d = number.lstrip("+")
    npa = d[1:4] if d.startswith("1") and len(d) == 11 else (d[:3] if len(d) == 10 else "")
    kind = "unknown"
    if npa in CARIBBEAN:
        kind = "caribbean"
    elif d.startswith(("1900", "190", "449", "09")) or npa == "900":
        kind = "premium"
    elif npa in TOLLFREE:
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


def brand_lookup(org: str) -> dict:
    return {"org": org, "hosts": verify.official_sites(org)}


def reputation(host: str) -> dict:
    return {"host": host, "notes": verify.enrich([host], limit=1)}


@dataclass(frozen=True)
class Spec:
    name: str
    arg: str  # what kind of argument: host | rail | phone | org
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
    Spec("brand_lookup", "org", brand_lookup, "Search the web for the real website of the company the message claims to be.", net=True, timeout=10, requires="TAVILY_API_KEY"),
    Spec("reputation", "host", reputation, "Search the web for scam reports about this website.", net=True, timeout=10, requires="TAVILY_API_KEY"),
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
    brand_sites: dict[str, list[str]] = field(default_factory=dict)  # org -> hostnames the web says are official
    web_notes: list[str] = field(default_factory=list)  # UNTRUSTED: shown as neutral notes, never weighed
    done: set = field(default_factory=set)  # (tool, arg) already answered

    @property
    def suspicious_hosts(self) -> list[str]:
        return list(dict.fromkeys([*self.hard_hosts, *self.soft_hosts]))

    def all_links_official(self) -> bool:
        return bool(self.hosts) and all(h in self.official_hosts for h in self.hosts)

    def all_links_established(self) -> bool:
        """Every link is either a known real site, or an old, resolving domain (2+ years): a link we have positive reason to trust."""
        return bool(self.hosts) and all(h in self.official_hosts or ((self.ages.get(h) or 0) >= 730 and self.dns.get(h) == "ok") for h in self.hosts)

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
        elif tool == "brand_lookup":
            self.brand_sites[arg] = d["hosts"]
        elif tool == "reputation":
            self.web_notes += d["notes"]

    def summary(self) -> str:
        parts = [f"{h}: {'; '.join(v)}" for h, v in {**self.soft_hosts, **self.hard_hosts}.items()]
        parts += [f"{h} is the real website of {b}" for h, b in self.official_hosts.items()]
        parts += [f"payment method '{r}' cannot be reversed" for r in self.irreversible_rails]
        parts += [f"{h} was registered {a} days ago" for h, a in self.ages.items() if a is not None]
        parts += [f"{h} does not resolve" for h, s in self.dns.items() if s == "nxdomain"]
        parts += [f"phone {p} looks like a {k} number" for p, k in self.phones.items() if k in ("caribbean", "premium")]
        parts += [f"the web lists {', '.join(h[:3])} as {o}'s official site" for o, h in self.brand_sites.items() if h]
        return "\n".join(parts) or "no deterministic findings"


# ---------------------------------------------------------------- the gate
_POOL = cf.ThreadPoolExecutor(max_workers=6, thread_name_prefix="bp-tool")


class ToolGate:
    def __init__(self, ing: Ingested, claimed_org: str, trace: Trace, budget: int = 6) -> None:
        self.ing, self.org, self.trace, self.budget, self.used = ing, (claimed_org or "").lower(), trace, budget, 0
        self.blocked: list[str] = []

    # -- validation ----------------------------------------------------------------------------------------------
    def _arg_ok(self, spec: Spec, arg: str) -> bool:
        e = self.ing.entities
        if spec.arg == "host":
            return arg in e.hosts and (not spec.net or is_public_hostname(arg))
        if spec.arg == "rail":
            return arg in e.rails
        if spec.arg == "phone":
            return arg in e.phones
        if spec.arg == "org":
            return bool(arg) and arg.lower() in ({self.org} | set(e.brands)) and arg.lower() in self.ing.text.lower()
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
            obs.record_tool(tool=spec.name, ok=True, ms=int((time.perf_counter() - t0) * 1000))
        except Exception as e:  # timeout, network, parse: a failed tool is a missing fact, never a crash
            f.done.add((spec.name, arg))
            obs.record_tool(tool=spec.name, ok=False, ms=int((time.perf_counter() - t0) * 1000), error=type(e).__name__)
            self.trace.add("tools", "skip", f"{spec.name} unavailable ({type(e).__name__}); continuing without it")


def initial_calls(ing: Ingested) -> list[tuple[str, str]]:
    """Round 0: everything local and free. Network lookups wait until the loop decides they're worth it."""
    e = ing.entities
    return ([("domain_check", h) for h in e.hosts[:3]] + [("payment_rail", r) for r in e.rails] + [("phone_check", p) for p in e.phones[:2]])


def run_tools(ing: Ingested, trace: Trace, claimed_org: str = "") -> tuple[Findings, ToolGate]:
    """Round 0 of the tool layer. Returns the findings and the gate (the loop reuses it for later rounds)."""
    f = Findings(hosts=list(ing.entities.hosts[:3]))
    gate = ToolGate(ing, claimed_org, trace)
    n = gate.run(initial_calls(ing), f)
    trace.add("tools", "flag" if f.suspicious_hosts or f.irreversible_rails else "pass", f"{n} local check(s); " + f.summary().replace("\n", " | "))
    return f, gate
