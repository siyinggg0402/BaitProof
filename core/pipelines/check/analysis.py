"""Stage 4, red-flag analysis. Rule-based tactics always run; the model (if configured) adds judgement.
Every tactic carries a QUOTE so the grounding gate can verify it."""
from __future__ import annotations

import re

from core.ai import fewshot, llm
from core.ai.prompts import CHECK_SYSTEM, CRITIC_SYSTEM
from core.domain import intents
from core.domain.schemas import TacticHit, Verdict
from core.domain.tactics import TACTICS, valid

from . import scenarios
from .evidence import Ledger
from .ingest import Ingested
from .intent import Intent
from .intent import CONSEQUENCE
from .knowledge import PREMIUM_RE, RULES
from .tools import Findings, registered_domain as tools_registered


STRONG_URGENCY = re.compile(r"\bwithin \d+ ?(?:hours?|hrs?|minutes?|mins?)|\bimmediately\b|\bact now\b|\bfinal (?:notice|demand|warning)\b|\blast (?:chance|warning)\b|\btoday (?:at|by)\b|\bby tonight\b|\bbefore midnight\b|\bright now\b", re.I)
STRONG_RULE_TACTICS = {"remote-access-request"}  # a pattern hit that is near-conclusive on its own


def rule_evidence(ing: Ingested, intent: Intent, f: Findings, ledger: Ledger) -> None:
    """Independent (non-model) evidence from phrase rules, the domain/rail tools and the intent diagnosis."""
    for tid, pats in RULES.items():
        for p in pats:
            if m := p.search(ing.text):
                q = m.group(0)[:80]
                strength = "strong" if tid in STRONG_RULE_TACTICS else "medium"
                if tid == "urgency-pressure" and not STRONG_URGENCY.search(ing.text):
                    strength = "weak"  # a lone "urgent" is how friends write too; deadlines with consequences are what scams use
                ledger.add("rule", "pattern", "scam", strength,
                           f"“{q}” is a known scam phrase ({TACTICS[tid]['label'].lower()})", q, tid)
                break
    for host, why in f.hard_hosts.items():
        ledger.add("tool", "domain_check", "scam", "strong", f"The link {host} {'; '.join(why)}", host, "lookalike-link")
    for host, why in f.soft_hosts.items():
        ledger.add("tool", "domain_check", "scam", "weak", f"The link {host} {'; '.join(why)}", host, "lookalike-link")
    for host, brand in f.official_hosts.items():
        ledger.add("tool", "domain_check", "safe", "medium", f"The link {host} goes to {brand.title()}'s real website", host)
    for host, age in f.ages.items():
        if age is None:
            continue
        if age < 30:
            ledger.add("tool", "domain_age", "scam", "medium", f"The website {host} was registered only {age} days ago", host, "lookalike-link")
        elif age < 180:
            ledger.add("tool", "domain_age", "scam", "weak", f"The website {host} was registered only {age} days ago (under six months)", host, "lookalike-link")
        elif age >= 730:
            ledger.add("tool", "domain_age", "safe", "weak", f"The website {host} has existed for {age // 365} years", host)
    for host, st in f.dns.items():
        if st == "nxdomain":
            ledger.add("tool", "dns_check", "scam", "weak", f"The website address {host} doesn't exist (any more)", host)
        elif st == "private":
            ledger.add("tool", "dns_check", "scam", "medium", f"{host} points to an internal address, which a real website never does", host)
    for org, sites in f.brand_sites.items():
        official = {tools_registered(h) for h in sites}
        labels = {r.split(".")[0] for r in official}  # amazon.co.uk and amazon.com are the same brand
        src = f.brand_src.get(org, "web search")
        for host in f.hosts:
            if host in f.official_hosts or not sites:
                continue
            reg = tools_registered(host)
            if reg in official or reg.split(".")[0] in labels:
                ledger.add("tool", "brand_lookup", "safe", "medium" if src == "wikidata" else "weak", f"{src.capitalize()} lists {host} as {org.title()}'s website", host)
            else:
                ledger.add("tool", "brand_lookup", "scam", "weak", f"{src.capitalize()} lists {sites[0]} as {org.title()}'s website, but this link goes to {host}", host, "lookalike-link")
    for num, kind in f.phones.items():
        if kind in ("caribbean", "premium"):
            why = "an area code tied to 'one-ring' scams" if kind == "caribbean" else "a premium-rate number that can charge you heavily"
            ledger.add("tool", "phone_check", "scam", "medium", f"The phone number is {why}", ing.entities.phone_raw.get(num, ""))
    for r in f.irreversible_rails:
        ledger.add("tool", "payment_rail", "scam", "strong", f"Asks for payment by {r.replace('-', ' ')}, which can't be taken back",
                   ing.entities.rails[r], "irreversible-payment")
    if "share_code" in intent.asks and intent.evidence.get("share_code"):
        ledger.add("intent", "ask:share_code", "scam", "strong", "Asks you to hand over a code that is the key to your account",
                   intent.evidence["share_code"], "otp-credential-phish")
    if "pay" in intent.asks and intent.pressure:
        # A plain bill reminder ("pay to avoid a late fee") is not a scam. It becomes hard evidence with an ultimatum, a threat, secrecy,
        # or somewhere unfamiliar to pay (a link, a phone number, an irreversible payment method).
        ultimatum = bool(CONSEQUENCE.search(ing.text)) or bool(intent.pressure_kinds & {"threat", "secrecy"}) or bool(ing.entities.hosts or ing.entities.phones or ing.entities.rails)
        ledger.add("intent", "ask:pay+pressure", "scam", "strong" if ultimatum else "medium", "Asks you to pay while rushing you",
                   intent.evidence.get("pressure", ""), None)
    if m := PREMIUM_RE.search(ing.text):
        ledger.add("rule", "premium-rate", "scam", "medium", "It advertises a premium-rate service (a short code, or a price per message or minute)", m.group(0)[:60], None)
    if intent.scenario:
        sc = scenarios.SCENARIOS[intent.scenario]
        ledger.add("intent", f"scenario:{sc.id}", "scam", "medium",
                   f"Follows the “{sc.label}” scam script ({intent.scenario_signs} of its {len(sc.signals)} telltale signs)", intent.evidence.get("scenario", ""), None)
    for text, quote, tactic in intent.mismatches:
        ledger.add("intent", "mismatch", "scam", "medium", text, quote, tactic)
    if intent.opener:
        ledger.add("intent", "opener", "scam", "weak", "It reads like the first step of a scam: an out-of-the-blue message that invites you to reply or move to another app",
                   intent.opener, None)
    if "secrecy" in intent.pressure_kinds:
        ledger.add("intent", "pressure:secrecy", "scam", "medium", "Tells you to keep it secret, so you can't check with anyone",
                   intent.evidence.get("pressure:secrecy", ""), "emotional-manipulation")
    if intent.model_scenario:
        ledger.add("model", "scenario", "scam", "weak", f"The AI reviewer thinks it follows the “{scenarios.SCENARIOS[intent.model_scenario].label}” scam script")
    if ing.injection:
        ledger.add("rule", "injection", "scam", "medium", "The message tries to give the checker instructions, which real messages never do")
    for note in f.web_notes:  # untrusted web text: shown, never weighed
        ledger.add("tool", "reputation", "neutral", "weak", "Web note (unverified): " + note[:200])


def safe_evidence(ing: Ingested, intent: Intent, ledger: Ledger, f: Findings | None = None) -> None:
    ledger.discard("benign-intent")  # re-evaluated every round: new red flags revoke it
    if f is not None and f.all_links_established() and not ledger.scam() and not intent.high_risk and not intent.pressure and not ing.injection:
        ledger.add("tool", "established-links", "safe", "medium", "Every link goes to a long-established website that exists")
    pur = intents.PURPOSES.get(intent.purpose)
    if (pur is not None and pur.clearable and not ledger.scam() and not intent.high_risk and not (intent.asks & {"click", "call", "pay"}) and not intent.pressure
            and not intent.opener and not intent.scenario and not intent.mismatches and not ing.injection
            and not (ing.entities.hosts or ing.entities.phones or ing.entities.rails) and intents.clearing_conditions_met(pur.id, ing.text, intent.asks)):
        # A deterministic, high-precision recognition of an ordinary message type (an OTP delivery, an appointment reminder, a delivery
        # update) with nothing risky in it: independent positive evidence, so rules alone may clear it.
        ledger.add("intent", f"purpose:{pur.id}", "safe", "medium", f"It reads as a normal {pur.label}: it informs you and asks for nothing risky")
    if not ledger.scam() and not intent.high_risk and "click" not in intent.asks and not intent.pressure and not ing.injection and not intent.opener:
        ledger.add("intent", "benign-intent", "safe", "medium", "It asks for nothing risky: no money, codes, passwords, links or installs, and it doesn't rush you")


SECOND_LOOK = ("\n\nSECOND LOOK: before deciding, weigh both explanations. List the strongest signs this is a scam AND the strongest signs it is a "
               "genuine message, then give your verdict. Do not assume the first impression is right, and do not invent red flags: if the message asks the reader for nothing, say so.")


def build_user(ing: Ingested, intent: Intent, f: Findings, second_look: bool = False, examples: bool | None = None) -> str:
    """Exactly what the analysis model is shown: the message, purpose guidance from the catalogue, intent facts, tool findings."""
    focus = intent.model_purpose if (intent.model_purpose and intents.PURPOSES[intent.model_purpose].risk == "risky") else intent.purpose
    guide = intents.guidance(focus)
    user = (f"MESSAGE:\n{ing.redacted}\n\nPURPOSE GUIDANCE (compare the message with both forms): {guide or 'n/a'}\n\n"
            f"INTENT (from rules): {intent.summary()}\nTOOL FINDINGS (trusted):\n{f.summary()}")
    if examples if examples is not None else fewshot.enabled():
        shots = fewshot.block(fewshot.retrieve(ing.redacted))  # similar labelled examples from the reference bank + this user's own library
        if shots:
            user += "\n\n" + shots
    if f.web_notes:
        user += "\n\nWEB NOTES (untrusted, may be wrong or planted):\n" + "\n".join(f.web_notes)
    return user + (SECOND_LOOK if second_look else "")


def model_analysis(ing: Ingested, intent: Intent, f: Findings, second_look: bool = False) -> dict | None:
    if not llm.available():
        return None
    try:
        return llm.chat_json(CHECK_SYSTEM, build_user(ing, intent, f, second_look), heavy=True, purpose="second-look" if second_look else "analysis")
    except llm.LLMUnavailable:
        return None


def parse_model(out: dict) -> tuple[Verdict, list[TacticHit]]:
    try:
        verdict = Verdict(out.get("verdict"))
        if verdict == Verdict.VICTIM:
            raise ValueError
    except ValueError:
        verdict = Verdict.UNSURE
    tactics = [TacticHit(id=t["id"], quote=str(t.get("quote", ""))[:120], why=str(t.get("why", ""))[:200])
               for t in out.get("tactics", []) if isinstance(t, dict) and valid(t.get("id", ""))]
    return verdict, tactics


LINK_WORDS = ("link", "url", "click", "website", "web address", "domain", "http")


def critic(ing: Ingested, intent: Intent, f: Findings | None = None) -> str | None:
    """Second opinion, run only when we're about to say 'safe'. Returns a concern, or None.
    The reviewer sees what our tools verified, and a concern about a link is dropped if every link has been verified."""
    if not llm.available():
        return None
    facts = f.summary() if f is not None else "none"
    try:
        out = llm.chat_json(CRITIC_SYSTEM, f"MESSAGE:\n{ing.redacted}\n\nINTENT: {intent.summary()}\nVERIFIED FACTS (trusted, from our own checks):\n{facts}",
                            heavy=True, purpose="critic")
    except llm.LLMUnavailable:
        return "second opinion unavailable"  # fail closed
    if not out.get("concern"):
        return None
    reason = str(out.get("reason") or "possible scam")
    if f is not None and (f.all_links_official() or f.all_links_established()) and any(w in reason.lower() for w in LINK_WORDS):
        return None  # we already verified every link; a generic 'there is a link' worry adds nothing
    return reason
