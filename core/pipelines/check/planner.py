"""The investigator: turns open questions into tool calls. The model may choose and order calls, but it can only pick from
candidates we derived from the message; the ToolGate still validates every one, and a deterministic plan is the fallback."""
from __future__ import annotations

from dataclasses import dataclass, field

from core.ai import llm
from core.ai.prompts import PLANNER_SYSTEM

from .evidence import Ledger
from .ingest import Ingested
from .intent import Intent
from .knowledge import SHORTENERS
from .tools import SPECS, Findings, ToolGate

MAX_CALLS_PER_ROUND = 4
ALWAYS = ("official_site_wikidata", "domain_owner")  # cheap, and each settles a question the others cannot: who the company is, and who registered the address. The model may add and order calls but not skip these


@dataclass
class Question:
    key: str
    text: str
    calls: list[tuple[str, str]] = field(default_factory=list)  # tools that could answer it


def open_questions(ing: Ingested, it: Intent, f: Findings, gate: ToolGate) -> list[Question]:
    """What would we still like to know? Only questions some available tool (or a re-check) could actually answer."""
    qs: list[Question] = []
    for url, dest in f.shorts.items():  # a short link says nothing about itself: where it goes comes first
        if not dest and gate.available("expand_link", url, f.done):
            qs.append(Question(f"short:{url}", f"Where does the short link {url[:60]} really go?", [("expand_link", url)]))
    unofficial = [h for h in f.hosts if h not in f.official_hosts and h not in SHORTENERS and not f.owned_by(h)]  # a shortener's own age and reputation are beside the point
    org = it.claimed if it.claimed_kind in ("organisation", "authority") else (ing.entities.brands[0] if ing.entities.brands else "")
    if not org and ing.origin and ing.origin.names():
        org = ing.origin.names()[0]  # the app or brand a screenshot showed
    if org and (unofficial or not f.orgs_real):  # a link to compare, or just: is this a real company? Asked first: it is cheap, and a registrant is compared with it
        calls = [(t, org) for t in ("official_site_wikidata", "brand_lookup") if gate.available(t, org, f.done)]
        if calls:
            qs.append(Question("brand", f"Is that link really {org}'s website?" if unofficial else f"Is {org} a real company?", calls))
    for h in unofficial:
        # cert_history is asked alongside domain_age (not after it): the registry often has no answer for a country domain, and a second round just to find
        # that out would use up the loop's round limit. Its evidence is only used when the registry gave no age.
        calls = [(t, h) for t in ("domain_age", "domain_owner", "dns_check", "cert_history", "reputation") if gate.available(t, h, f.done)]
        if calls:
            qs.append(Question(f"host:{h}", f"Is {h} a trustworthy website?", calls))
    if it.disagreements:
        qs.append(Question("recheck", "The rules and the AI disagree about what kind of scam this is: " + "; ".join(it.disagreements)))
    return qs


def deterministic_plan(qs: list[Question]) -> list[tuple[str, str]]:
    seen, out = set(), []
    for q in qs:
        for c in q.calls:
            if c not in seen:
                seen.add(c)
                out.append(c)
    return out[:MAX_CALLS_PER_ROUND]


def llm_plan(ing: Ingested, qs: list[Question], ledger: Ledger, gate: ToolGate, f: Findings) -> tuple[list[tuple[str, str]], str]:
    """(calls, who decided). Falls back to the deterministic plan if the model is off, fails, or proposes nothing usable."""
    fallback = deterministic_plan(qs)
    candidates = {c for q in qs for c in q.calls}
    if not llm.available() or not candidates:
        return fallback, "rules"
    tools_text = "\n".join(f"- {n}: {SPECS[n].desc}" for n in sorted({c[0] for c in candidates}))
    qtext = "\n".join(f"- {q.text} (candidate calls: {', '.join(f'{t}({a})' for t, a in q.calls) or 'none'})" for q in qs)
    claims = "\n".join(f"- [{e.supports}/{e.strength}] {e.claim}" for e in ledger.items[:12]) or "- none yet"
    user = f"MESSAGE:\n{ing.redacted}\n\nEVIDENCE SO FAR:\n{claims}\n\nOPEN QUESTIONS:\n{qtext}\n\nTOOLS:\n{tools_text}"
    try:
        out = llm.chat_json(PLANNER_SYSTEM, user, heavy=False, purpose="planner")
    except llm.LLMUnavailable:
        return fallback, "rules"
    picked, seen = [], set()
    for c in out.get("calls", []) if isinstance(out.get("calls"), list) else []:
        if isinstance(c, dict):
            key = (str(c.get("tool", "")), str(c.get("arg", "")))
            if key in candidates and key not in seen:  # only calls we offered: the model can't invent tools or arguments
                seen.add(key)
                picked.append(key)
    if not picked:
        return fallback, "rules"
    must = [c for q in qs for c in q.calls if c[0] in ALWAYS and c not in picked]  # offered, and the model left them out
    return ((must + picked)[:MAX_CALLS_PER_ROUND], "model")
