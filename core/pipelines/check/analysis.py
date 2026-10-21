"""Stage 4, red-flag analysis. Rule-based tactics always run; the model (if configured) adds judgement.
Every tactic carries a QUOTE so the grounding gate can verify it."""
from __future__ import annotations

import re

from core.ai import fewshot, llm
from core.ai.prompts import CHECK_SYSTEM, CRITIC_SYSTEM
from core.domain import intents
from core.lang import ms as MS
from core.lang import zh as ZH
from core.lang.i18n import PROMPT_NAMES, tactic_text, tr, why as why_text
from core.lang.text import Dual
from core.domain.schemas import TacticHit, Verdict
from core.domain.tactics import TACTICS, valid

from . import scenarios
from .evidence import Ledger
from .ingest import Ingested
from .intent import Intent
from .intent import CONSEQUENCE
from .knowledge import FREE_MAIL, PREMIUM_RE, RULES
from .tools import Findings, registered_domain as tools_registered


STRONG_URGENCY = Dual(r"\bwithin \d+ ?(?:hours?|hrs?|minutes?|mins?)|\bimmediately\b|\bact now\b|\bfinal (?:notice|demand|warning)\b|\blast (?:chance|warning)\b|\btoday (?:at|by)\b|\bby tonight\b|\bbefore midnight\b|\bright now\b", ZH.STRONG_DEADLINE, MS.STRONG_DEADLINE)
_WARNING = Dual(None, ZH.WARNING_SENTENCE, MS.WARNING_SENTENCE)  # warnings and public notices are not the scam they quote
STRONG_RULE_TACTICS = {"remote-access-request"}  # a pattern hit that is near-conclusive on its own


FREE_MAIL_SCRIPTS = {"prize-lottery", "inheritance-advance-fee", "job-task", "investment", "government-rebate", "claim-approved", "overpayment", "charity-appeal"}


# Words that mean the message is about money, an account or something to claim or verify. "Right now" next to one of these is pressure; next to
# "leaving" or "the phone" it is just a friend talking.
TRANSACTIONAL = re.compile(r"\b(?:pay\w*|account|card|loan|bills?|dues?|prize|cashback|claim\w*|verif\w+|transactions?|identity|suspen\w+|penalt\w+|disconnect\w*|customs|insurance|payout|"
                           r"salary|cv|resume|details|information|password|login|otp|code|bank|refund|legal|unauthori[sz]ed|suspicious|offer|reward|winner|won|fee|charge\w*|balance|"
                           r"upgrade|activate|expire\w*|block\w*|locked|delivery|parcel|order|invest\w*|profit|transfer|deposit|crypto|bitcoin|gift ?cards?)\b", re.I)


def _something_is_asked(ing: Ingested, intent: Intent) -> bool:
    """Is the message about something that matters: a risky request, a link, a number to call, a consequence, or money / an account / a claim / a verification?"""
    return bool(intent.high_risk or "click" in intent.asks or ("call" in intent.asks and (ing.entities.phones or ing.entities.hosts)) or CONSEQUENCE.search(ing.text)
                or TRANSACTIONAL.search(ing.text))


def rule_evidence(ing: Ingested, intent: Intent, f: Findings, ledger: Ledger) -> None:
    """Independent (non-model) evidence from phrase rules, the domain/rail tools and the intent diagnosis."""
    L = ing.reply
    T = lambda s, **kw: tr(s, L, **kw)  # noqa: E731
    asked = _something_is_asked(ing, intent)
    # "don't tell" and friends are the heart of a family-emergency or impersonation scam, but also how friends gossip: they need a request, a claimed
    # identity, a known script or a payment method next to them to count as more than a hint.
    risky_context = asked or bool(intent.claimed_kind or intent.scenario or ing.entities.rails)
    scan = _WARNING.sub(" ", ing.text)  # "请勿将验证码告知他人" warns against the very thing it names
    for tid, pats in RULES.items():
        for p in pats:
            if m := p.search(scan):
                q = m.group(0)[:80]
                strength = "strong" if tid in STRONG_RULE_TACTICS else "medium"
                if tid == "urgency-pressure" and not (STRONG_URGENCY.search(ing.text) and asked):
                    strength = "weak"  # "leaving right now" and a lone "urgent" are how friends write too; a deadline matters when it is attached to a request
                if tid == "emotional-manipulation" and not risky_context:
                    strength = "weak"
                ledger.add("rule", "pattern", "scam", strength,
                           T("“{q}” is a known scam phrase ({label})", q=q, label=tactic_text(tid, "label", L, TACTICS).lower()), q, tid)
                break
    for host, why in f.hard_hosts.items():
        ledger.add("tool", "domain_check", "scam", "strong", T("The link {host} {why}", host=host, why="; ".join(why_text(w, L) for w in why)), host, "lookalike-link")
    for host, why in f.soft_hosts.items():
        ledger.add("tool", "domain_check", "scam", "weak", T("The link {host} {why}", host=host, why="; ".join(why_text(w, L) for w in why)), host, "lookalike-link")
    for host, brand in f.official_hosts.items():
        ledger.add("tool", "domain_check", "safe", "medium", T("The link {host} goes to {brand}'s real website", host=host, brand=brand.title()), host)
    for host, age in f.ages.items():
        if age is None:
            continue
        if age < 30:
            ledger.add("tool", "domain_age", "scam", "medium", T("The website {host} was registered only {age} days ago", host=host, age=age), host, "lookalike-link")
        elif age < 180:
            ledger.add("tool", "domain_age", "scam", "weak", T("The website {host} was registered only {age} days ago (under six months)", host=host, age=age), host, "lookalike-link")
        elif age >= 730:
            ledger.add("tool", "domain_age", "safe", "weak", T("The website {host} has existed for {years} years", host=host, years=age // 365), host)
    for host, st in f.dns.items():
        if st == "nxdomain":
            ledger.add("tool", "dns_check", "scam", "weak", T("The website address {host} doesn't exist (any more)", host=host), host)
        elif st == "private":
            ledger.add("tool", "dns_check", "scam", "medium", T("{host} points to an internal address, which a real website never does", host=host), host)
    for org, sites in f.brand_sites.items():
        official = {tools_registered(h) for h in sites}
        labels = {r.split(".")[0] for r in official}  # amazon.co.uk and amazon.com are the same brand
        src = f.brand_src.get(org, "web search")
        for host in f.hosts:
            if host in f.official_hosts or not sites:
                continue
            reg = tools_registered(host)
            if reg in official or reg.split(".")[0] in labels:
                ledger.add("tool", "brand_lookup", "safe", "medium" if src == "wikidata" else "weak", T("{src} lists {host} as {org}'s website", src=src.capitalize(), host=host, org=org.title()), host)
            else:
                ledger.add("tool", "brand_lookup", "scam", "weak", T("{src} lists {site} as {org}'s website, but this link goes to {host}", src=src.capitalize(), site=sites[0], org=org.title(), host=host), host, "lookalike-link")
    for num, kind in f.phones.items():
        if kind in ("caribbean", "premium"):
            why = T("an area code tied to 'one-ring' scams") if kind == "caribbean" else T("a premium-rate number that can charge you heavily")
            ledger.add("tool", "phone_check", "scam", "medium", T("The phone number is {why}", why=why), ing.entities.phone_raw.get(num, ""))
    for r in f.irreversible_rails:
        ledger.add("tool", "payment_rail", "scam", "strong", T("Asks for payment by {rail}, which can't be taken back", rail=T(r.replace('-', ' '))),
                   ing.entities.rails[r], "irreversible-payment")
    if "share_code" in intent.asks and intent.evidence.get("share_code"):
        ledger.add("intent", "ask:share_code", "scam", "strong", T("Asks you to hand over a code that is the key to your account"),
                   intent.evidence["share_code"], "otp-credential-phish")
    if "pay" in intent.asks and intent.pressure:
        # A plain bill reminder ("pay to avoid a late fee") is not a scam. It becomes hard evidence with an ultimatum, a threat, secrecy,
        # or somewhere unfamiliar to pay (a link, a phone number, an irreversible payment method).
        ultimatum = bool(CONSEQUENCE.search(ing.text)) or bool(intent.pressure_kinds & {"threat", "secrecy"}) or bool(ing.entities.hosts or ing.entities.phones or ing.entities.rails)
        ledger.add("intent", "ask:pay+pressure", "scam", "strong" if ultimatum else "medium", T("Asks you to pay while rushing you"),
                   intent.evidence.get("pressure", ""), None)
    if m := PREMIUM_RE.search(ing.text):
        ledger.add("rule", "premium-rate", "scam", "medium", T("It advertises a premium-rate service (a short code, or a price per message or minute)"), m.group(0)[:60], None)
    if intent.scenario:
        sc = scenarios.SCENARIOS[intent.scenario]
        ledger.add("intent", f"scenario:{sc.id}", "scam", "medium",
                   T("Follows the “{label}” scam script ({n} of its {m} telltale signs)", label=T(sc.label), n=intent.scenario_signs, m=len(sc.signals)), intent.evidence.get("scenario", ""), None)
    for text, quote, tactic in intent.mismatches:
        ledger.add("intent", "mismatch", "scam", "medium", text, quote, tactic)
    if intent.opener:
        ledger.add("intent", "opener", "scam", "weak", T("It reads like the first step of a scam: an out-of-the-blue message that invites you to reply or move to another app"),
                   intent.opener, None)
    if "secrecy" in intent.pressure_kinds and risky_context:  # without a request, identity or script it is gossip, and the phrase rule has already noted it as a hint
        ledger.add("intent", "pressure:secrecy", "scam", "medium", T("Tells you to keep it secret, so you can't check with anyone"),
                   intent.evidence.get("pressure:secrecy", ""), "emotional-manipulation")
    free = [e for e in ing.entities.emails if e.rsplit("@", 1)[-1] in FREE_MAIL]
    if free and (intent.claimed_kind in ("authority", "organisation") or intent.scenario in FREE_MAIL_SCRIPTS):
        ledger.add("intent", "free-mail-contact", "scam", "medium", T("Wants you to reply to a free email address while claiming to be an organisation or offering a prize, job or loan"),
                   free[0], None)
    if intent.model_scenario:
        ledger.add("model", "scenario", "scam", "weak", T("The AI reviewer thinks it follows the “{label}” scam script", label=T(scenarios.SCENARIOS[intent.model_scenario].label)))
    if ing.injection:
        ledger.add("rule", "injection", "scam", "medium", T("The message tries to give the checker instructions, which real messages never do"))
    for note in f.web_notes:  # untrusted web text: shown, never weighed
        ledger.add("tool", "reputation", "neutral", "weak", T("Web note (unverified): {note}", note=note[:200]))


def safe_evidence(ing: Ingested, intent: Intent, ledger: Ledger, f: Findings | None = None) -> None:
    T = lambda s, **kw: tr(s, ing.reply, **kw)  # noqa: E731
    ledger.discard("benign-intent")  # re-evaluated every round: new red flags revoke it
    if not ing.english:
        return  # our rules cannot read this language, so "the rules found nothing risky" would be a claim about text they never understood
    if f is not None and f.all_links_established() and not ledger.scam() and not intent.high_risk and not intent.pressure and not ing.injection:
        ledger.add("tool", "established-links", "safe", "medium", T("Every link goes to a long-established website that exists"))
    pur = intents.PURPOSES.get(intent.purpose)
    if (pur is not None and pur.clearable and not ledger.scam() and not intent.high_risk and not (intent.asks & {"click", "call", "pay"}) and not intent.pressure
            and not intent.opener and not intent.scenario and not intent.mismatches and not ing.injection
            and not (ing.entities.hosts or ing.entities.phones or ing.entities.rails) and intents.clearing_conditions_met(pur.id, ing.text, intent.asks)):
        # A deterministic, high-precision recognition of an ordinary message type (an OTP delivery, an appointment reminder, a delivery
        # update) with nothing risky in it: independent positive evidence, so rules alone may clear it.
        ledger.add("intent", f"purpose:{pur.id}", "safe", "medium", T("It reads as a normal {label}: it informs you and asks for nothing risky", label=T(pur.label)))
    if not ledger.scam() and not intent.high_risk and "click" not in intent.asks and not intent.pressure and not ing.injection and not intent.opener:
        ledger.add("intent", "benign-intent", "safe", "medium", T("It asks for nothing risky: no money, codes, passwords, links or installs, and it doesn't rush you"))


SECOND_LOOK = ("\n\nSECOND LOOK: before deciding, weigh both explanations. List the strongest signs this is a scam AND the strongest signs it is a "
               "genuine message, then give your verdict. Do not assume the first impression is right, and do not invent red flags: if the message asks the reader for nothing, say so.")


def reply_language_line(ing: Ingested) -> str:
    """Tell the model which language to explain in, but only when that differs from the message's own: the instruction is not free (measured: on
    Chinese messages, adding it to every check cleared 5 fewer of 40 genuine messages), and the prompt already says 'the message's language' by default."""
    return f"\n\nREPLY LANGUAGE: {PROMPT_NAMES[ing.reply]}" if ing.reply != ing.lang else ""


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
    user += reply_language_line(ing)
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


LINK_WORDS = ("link", "url", "click", "website", "web address", "domain", "http", "链接", "網址", "网址", "网站", "點擊", "点击", "連結", "連接")


def critic(ing: Ingested, intent: Intent, f: Findings | None = None) -> str | None:
    """Second opinion, run only when we're about to say 'safe'. Returns a concern, or None.
    The reviewer sees what our tools verified, and a concern about a link is dropped if every link has been verified."""
    if not llm.available():
        return None
    facts = f.summary() if f is not None else "none"
    try:
        out = llm.chat_json(CRITIC_SYSTEM, f"MESSAGE:\n{ing.redacted}\n\nINTENT: {intent.summary()}\nVERIFIED FACTS (trusted, from our own checks):\n{facts}{reply_language_line(ing)}",
                            heavy=True, purpose="critic")
    except llm.LLMUnavailable:
        return "second opinion unavailable"  # fail closed
    if not out.get("concern"):
        return None
    reason = str(out.get("reason") or "possible scam")
    if f is not None and (f.all_links_official() or f.all_links_established()) and any(w in reason.lower() for w in LINK_WORDS):
        return None  # we already verified every link; a generic 'there is a link' worry adds nothing
    return reason
