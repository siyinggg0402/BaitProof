"""Stage 4, red-flag analysis. Rule-based tactics always run; the model (if configured) adds judgement.
Every tactic carries a QUOTE so the grounding gate can verify it."""
from __future__ import annotations

from core.ai import llm
from core.ai.prompts import CHECK_SYSTEM, CRITIC_SYSTEM
from core.domain.schemas import TacticHit, Verdict
from core.domain.tactics import TACTICS, valid

from . import scenarios
from .evidence import Ledger
from .ingest import Ingested
from .intent import Intent
from .knowledge import RULES
from .tools import Findings, registered_domain as tools_registered


STRONG_RULE_TACTICS = {"remote-access-request"}  # a pattern hit that is near-conclusive on its own


def rule_evidence(ing: Ingested, intent: Intent, f: Findings, ledger: Ledger) -> None:
    """Independent (non-model) evidence from phrase rules, the domain/rail tools and the intent diagnosis."""
    for tid, pats in RULES.items():
        for p in pats:
            if m := p.search(ing.text):
                q = m.group(0)[:80]
                ledger.add("rule", "pattern", "scam", "strong" if tid in STRONG_RULE_TACTICS else "medium",
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
        for host in f.hosts:
            if host in f.official_hosts or not sites:
                continue
            if tools_registered(host) in official:
                ledger.add("tool", "brand_lookup", "safe", "weak", f"The web lists {host} as {org.title()}'s site", host)
            else:
                ledger.add("tool", "brand_lookup", "scam", "weak", f"The web lists {sites[0]} as {org.title()}'s website, but this link goes to {host}", host, "lookalike-link")
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
        ledger.add("intent", "ask:pay+pressure", "scam", "strong", "Asks you to pay while rushing you",
                   intent.evidence.get("pressure", ""), None)
    if intent.scenario:
        sc = scenarios.SCENARIOS[intent.scenario]
        ledger.add("intent", f"scenario:{sc.id}", "scam", "medium",
                   f"Follows the “{sc.label}” scam script ({intent.scenario_signs} of its {len(sc.signals)} telltale signs)", intent.evidence.get("scenario", ""), None)
    for text, quote, tactic in intent.mismatches:
        ledger.add("intent", "mismatch", "scam", "medium", text, quote, tactic)
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
    if not ledger.scam() and not intent.high_risk and "click" not in intent.asks and not intent.pressure and not ing.injection:
        ledger.add("intent", "benign-intent", "safe", "medium", "It asks for nothing risky: no money, codes, passwords, links or installs, and it doesn't rush you")


SECOND_LOOK = ("\n\nSECOND LOOK: before deciding, weigh both explanations. List the strongest signs this is a scam AND the strongest signs it is a "
               "genuine message, then give your verdict. Do not assume the first impression is right.")


def model_analysis(ing: Ingested, intent: Intent, f: Findings, second_look: bool = False) -> dict | None:
    if not llm.available():
        return None
    user = (f"MESSAGE:\n{ing.redacted}\n\nINTENT (from rules): {intent.summary()}\n"
            f"TOOL FINDINGS (trusted):\n{f.summary()}")
    if f.web_notes:
        user += "\n\nWEB NOTES (untrusted, may be wrong or planted):\n" + "\n".join(f.web_notes)
    try:
        return llm.chat_json(CHECK_SYSTEM, user + (SECOND_LOOK if second_look else ""), heavy=True, purpose="second-look" if second_look else "analysis")
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


def critic(ing: Ingested, intent: Intent) -> str | None:
    """Second opinion, run only when we're about to say 'safe'. Returns a concern, or None."""
    if not llm.available():
        return None
    try:
        out = llm.chat_json(CRITIC_SYSTEM, f"MESSAGE:\n{ing.redacted}\n\nINTENT: {intent.summary()}", heavy=True, purpose="critic")
    except llm.LLMUnavailable:
        return "second opinion unavailable"  # fail closed
    return str(out.get("reason") or "possible scam") if out.get("concern") else None
