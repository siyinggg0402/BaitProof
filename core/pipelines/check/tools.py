"""Stage 3, tool-calling gate. Tools are allowlisted; arguments must come from entities extracted from the
message (never model-invented); calls are budgeted; web results are untrusted and can only add suspicion."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.ai import verify
from core.storage import library

from .ingest import Entities, Ingested
from .knowledge import BAD_TLDS, BRANDS, LEET, SHORTENERS
from .trace import Trace

IRREVERSIBLE = {"gift-card", "crypto", "wire", "safe-account"}


def _is_official(host: str, official: str) -> bool:
    return host == official or host.endswith("." + official) or (official.endswith(".gov") and host.endswith(".gov"))


def domain_check(host: str) -> dict:
    """Deterministic lookalike analysis. 'hard' flags are near-certain (brand impersonation); 'soft' are just odd."""
    tokens = set()
    for variant in (host.translate(LEET), host.translate(LEET).replace("1", "l"), host.translate(LEET).replace("1", "i")):
        tokens |= set(re.split(r"[.\-]", variant))
        tokens.add(variant.replace("-", "").replace(".", ""))
    hard, soft = [], []
    brand = next((b for b in BRANDS if b in tokens or any(len(b) >= 5 and b in t for t in tokens)), None)
    if brand and not _is_official(host, BRANDS[brand]):
        hard.append(f"imitates {brand} but is not {BRANDS[brand]}")
    if "xn--" in host:
        hard.append("uses disguised (punycode) characters")
    if re.fullmatch(r"[\d.]+", host):
        hard.append("is a raw IP address")
    if host in SHORTENERS:
        soft.append("is a link shortener that hides the real address")
    if host.endswith(BAD_TLDS):
        soft.append(f"ends in {host[host.rfind('.'):]}, common in throwaway scam sites")
    if host.count("-") >= 3:
        soft.append("has many hyphens")
    return {"host": host, "hard": hard, "soft": soft}


def payment_rail(rail: str) -> dict:
    return {"rail": rail, "irreversible": rail in IRREVERSIBLE}


def reputation(host: str) -> dict:
    return {"host": host, "notes": verify.enrich([host], limit=1)}


TOOLS = {"domain_check": domain_check, "payment_rail": payment_rail, "reputation": reputation}


@dataclass
class Findings:
    hard_hosts: dict[str, list[str]] = field(default_factory=dict)
    soft_hosts: dict[str, list[str]] = field(default_factory=dict)
    irreversible_rails: list[str] = field(default_factory=list)
    web_notes: list[str] = field(default_factory=list)  # UNTRUSTED: only ever fed to the model as context

    @property
    def suspicious_hosts(self) -> list[str]:
        return list(dict.fromkeys([*self.hard_hosts, *self.soft_hosts]))

    def summary(self) -> str:
        parts = [f"{h}: {'; '.join(v)}" for h, v in {**self.soft_hosts, **self.hard_hosts}.items()]
        parts += [f"payment method '{r}' cannot be reversed" for r in self.irreversible_rails]
        return "\n".join(parts) or "no deterministic findings"


class ToolGate:
    def __init__(self, ent: Entities, trace: Trace, budget: int = 5) -> None:
        self.ent, self.trace, self.budget, self.used = ent, trace, budget, 0

    def call(self, name: str, arg: str) -> dict | None:
        if name not in TOOLS:
            self.trace.add("tools", "block", f"unknown tool '{name}' refused")
            return None
        allowed = self.ent.rails if name == "payment_rail" else self.ent.hosts
        if arg not in allowed:
            self.trace.add("tools", "block", f"{name}: argument was not found in the message")
            return None
        if self.used >= self.budget:
            self.trace.add("tools", "block", f"{name}: tool budget ({self.budget}) used up")
            return None
        self.used += 1
        try:
            return TOOLS[name](arg)
        except Exception:
            self.trace.add("tools", "skip", f"{name} failed; continuing without it")
            return None


def run_tools(ing: Ingested, trace: Trace) -> Findings:
    """Deterministic planner. Every call still goes through the gate, so an LLM planner could replace it safely."""
    gate, f = ToolGate(ing.entities, trace), Findings()
    for host in ing.entities.hosts[:3]:
        if r := gate.call("domain_check", host):
            if r["hard"]:
                f.hard_hosts[host] = r["hard"]
            elif r["soft"]:
                f.soft_hosts[host] = r["soft"]
    for rail in ing.entities.rails:
        if (r := gate.call("payment_rail", rail)) and r["irreversible"]:
            f.irreversible_rails.append(rail)
    unverified = f.suspicious_hosts[:1] or ing.entities.hosts[:1]
    for host in unverified:
        if r := gate.call("reputation", host):
            f.web_notes += r["notes"]
    trace.add("tools", "flag" if f.suspicious_hosts or f.irreversible_rails else "pass",
              f"{gate.used} tool call(s); " + (f.summary().replace("\n", " | ")))
    return f
