"""Stage 2, intent diagnosis: what is the sender asking the reader to DO, under what pressure, as whom?
Scams ask for an action under pressure; legitimate messages mostly inform. This is the main discriminator."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.ai import llm
from core.domain import intents
from core.domain import zh as ZH
from core.domain.i18n import tr
from core.domain.lang import CJK, Dual, Z, canon
from core.ai.prompts import INTENT_SYSTEM

from .ingest import Ingested
from . import scenarios
from .knowledge import C, PRESSURE_RE

ASKS = ("pay", "share_code", "share_credentials", "install", "click", "call", "reply")
HIGH_RISK_ASKS = {"pay", "share_code", "share_credentials", "install"}

ASK_RULES = {
    "pay": Dual(r"\b(?:txt|text|sms|send|reply)\b[^.!?\n]{0,70}\b(?:to|2)\s*\d{4,6}\b|\b(?:pay|send|transfer|wire|deposit|top up|buy|move)\b[^.!?\n]{0,40}(?:[$€£]|\d+ ?(?:dollars|usd|eur)|\bfee\b|\btax\b|gift ?cards?|bitcoin|crypto|usdt|voucher|balance|savings|money|cash)|\bpag(?:ue|ar)\b|\b(?:send|return|refund|pay|transfer) (?:it|that|the money|the funds|them) back\b", ZH.ASK["pay"]),
    "share_code": Dual(r"\b(?:repl(?:y|ying)|send(?:ing)?|read|shar(?:e|ing)|giv(?:e|ing)|forward|tell|submit(?:ting)?|provid(?:e|ing)|enter(?:ing)?)\b[^.!?\n]{0,25}\b(?:code|otp|pin)\b|\bread (?:it|them) (?:out )?to me\b", ZH.ASK["share_code"]),
    "share_credentials": Dual(r"\b(?:enter|confirm|verify|provide|share|give|send|need|require|ask(?:ed)? for)\s+(?:only |just )?(?:us |me )?(?:your |the )?(?:password|pin|ssn|social security number|card number|medicare number|date of birth|bank details|login|(?:personal |bank |card |account |contact |full )?(?:details|info(?:rmation)?|id\b))", ZH.ASK["share_credentials"]),
    "install": Dual(r"\binstall\b|\bdownload (?:the |this )?(?:app|software)\b", ZH.ASK["install"]),
    "click": Dual(r"\b(?:click|tap|open)\b[^.!?\n]{0,15}\b(?:link|here)\b", ZH.ASK["click"]),
    "call": Dual(r"\bcall\b", ZH.ASK["call"]),
    "reply": Dual(r"\breply\b|\brespond\b", ZH.ASK["reply"]),
}
NEGATION = Dual(r"\b(?:never|don'?t|do not|won'?t|will not)\b[^.!?]{0,25}$", ZH.NEGATION)
RELATIONS = Dual(r"\b(mum|mom|dad|grandma|grandpa|nan|nana|gran|son|daughter|grandson|granddaughter|it'?s me)\b", ZH.RELATIONS)
AUTHORITY = Dual(r"\b(officer|detective|police|irs|hmrc|social security|court|tax office|government|cyber ?crime|fraud department|security team)\b", ZH.AUTHORITY)
ORGANISATION = Dual(r"\b((?:your|the) bank(?! (?:details|account|transfer|statement|holiday|balance))|bank (?:alert|notice|security|team|fraud)|\w+ bank(?! (?:details|account|transfer|statement|holiday))|microsoft|apple|amazon|paypal|netflix|your provider|support team|customer service)\b", ZH.ORGANISATION)
OPENER = Dual(
    r"\b[Ii]s this [A-Z][a-z]+\s*\?|\bwrong (?:person|number)\b|\b(?:got|found|have) your (?:number|email|contact|details) (?:from|through|via|on)\b"
    r"|\b(?:gave|sent|passed|shared|given) (?:me|us) your (?:number|email|contact|details|address)\b|\bfriend of (?:your|a (?:friend|colleague))\b|\bmutual (?:friend|contact|acquaintance)\b"
    r"|\b(?:this is )?my (?:new|temporary|temp|other) (?:number|phone)\b|\bnew number\b|\btemporary number\b|\b(?:lost|dropped|broke|cracked|smashed) my phone\b|\bphone (?:broke|died|fell)\b"
    r"|\bcan you (?:check|confirm|see) (?:if )?you can (?:receive|get)\b|\bare you (?:available|at your desk)\b"
    r"|\b(?:add me on|message me on|find me on|move (?:to|this to)|continue (?:on|in)) (?:telegram|whatsapp|signal|wechat)\b"
    r"|\b(?:is (?:the|this) item|is it) still (?:available|for sale)\b|\bstill available\b"
    r"|\b(?:saw|found|came across|noticed) your (?:profile|listing|ad|post|resume|cv)\b|\b(?:text|call|message) me (?:on|at) \+?[\d(]", ZH.OPENER)

PRESSURE_KINDS = {
    "deadline": PRESSURE_RE,
    "threat": Dual(r"\b(?:arrest\w*|warrant|court|legal action|lawsuit|account (?:will be )?(?:closed|suspended|blocked|deactivated)|disconnect\w*|detain\w*|penalty|lose access)\b", ZH.THREAT),
    "secrecy": Dual(r"\b(?:don'?t tell|do not tell|keep (?:this|it) (?:a )?secret|between us|do not (?:speak|talk) to|don'?t call|please don'?t call)\b", ZH.SECRECY),
    "emotional": Dual(r"\b(?:emergency|hospital|in trouble|stuck|please hurry|i love you|lonely|bail|accident)\b", ZH.EMOTIONAL),
}
_PAY_VERB = Dual(r"\b(?:buy|send|pay)\b", r"转|汇|付|买|购|支付|充值|缴")
_NEW_NUMBER = Dual(r"\b(?:new (?:number|phone)|lost my|dropped my phone)\b", ZH.NEW_NUMBER)


@dataclass
class Intent:
    asks: set[str] = field(default_factory=set)
    pressure_kinds: set[str] = field(default_factory=set)
    claimed: str = ""  # who the sender says they are
    claimed_kind: str = ""  # authority | organisation | relation
    scenario: str = ""  # a known scam script this follows (rules), see scenarios.py
    scenario_signs: int = 0
    model_scenario: str = ""  # what the model thinks, kept apart because it is weaker evidence
    mismatches: list[tuple] = field(default_factory=list)  # (plain text, quote, tactic)
    evidence: dict[str, str] = field(default_factory=dict)  # ask/pressure/identity/scenario -> quoted text
    disagreements: list[str] = field(default_factory=list)  # rules vs model: an open question for the confidence loop
    opener: str = ""  # quote of an out-of-the-blue first-contact phrase (the usual first step of a scam)
    purpose: str = ""  # what the message is FOR, chosen by rules from the closed catalogue (core/domain/intents.py)
    model_purpose: str = ""  # the model's choice from the same catalogue, kept only if the text supports it
    used_ai: bool = False

    @property
    def pressure(self) -> bool:
        return bool(self.pressure_kinds)

    @property
    def high_risk(self) -> set[str]:
        return self.asks & HIGH_RISK_ASKS

    def summary(self) -> str:
        who = f"{self.claimed} ({self.claimed_kind})" if self.claimed else "unknown"
        sc = (f"; follows_script={self.scenario}" if self.scenario else "") + ("; first-contact opener" if self.opener else "")
        pur = self.purpose + (f" (model: {self.model_purpose})" if self.model_purpose and self.model_purpose != self.purpose else "")
        return f"purpose={pur or 'unknown'}; asks={sorted(self.asks) or 'nothing'}; pressure={sorted(self.pressure_kinds) or 'none'}; claims_to_be={who}{sc}"


def _heuristic(ing: Ingested) -> Intent:
    it = Intent()
    for ask, pat in ASK_RULES.items():
        for m in pat.finditer(ing.text):
            if not NEGATION.search(ing.text[max(0, m.start() - 40) : m.start()]):
                it.asks.add(ask)
                it.evidence.setdefault(ask, m.group(0)[:80])
                break
    if ing.entities.hosts:
        it.asks.add("click")
    if ing.entities.rails and "pay" not in it.asks and _PAY_VERB.search(ing.text):
        it.asks.add("pay")
    for kind, pat in PRESSURE_KINDS.items():
        if m := pat.search(ing.text):
            it.pressure_kinds.add(kind)
            it.evidence.setdefault("pressure", m.group(0)[:80])
            it.evidence[f"pressure:{kind}"] = m.group(0)[:80]
    for kind, pat in (("authority", AUTHORITY), ("organisation", ORGANISATION), ("relation", RELATIONS)):
        m = pat.search(ing.text)
        if m is None and kind == "organisation" and ing.entities.brands:
            m = re.search(re.escape(ing.entities.brands[0]), ing.text, re.I)
            if m is None and ing.entities.brand_quotes:  # a Chinese brand name ("支付宝") rather than its Latin key
                m = Z(re.escape(next(iter(ing.entities.brand_quotes.values())))).search(ing.text)
        if m:
            it.claimed, it.claimed_kind = m.group(0).lower(), kind
            it.evidence["identity"] = m.group(0)
            break
    if m := OPENER.search(ing.text):
        it.opener = m.group(0)[:80]
    it.scenario, it.scenario_signs, q = scenarios.detect(ing.text)
    if it.scenario:
        it.evidence["scenario"] = q
    _mismatches(it, ing)
    it.purpose = classify_purpose(ing, it)
    return it


def _mismatches(it: Intent, ing: Ingested) -> None:
    """Claim-vs-ask contradictions: the pattern real senders almost never produce."""
    who, kind = it.claimed, it.claimed_kind
    T = lambda s, **kw: tr(s, ing.reply, **kw)  # noqa: E731
    if kind in ("authority", "organisation"):
        if ing.entities.rails:
            rail = next(iter(ing.entities.rails))
            it.mismatches.append((T("Claims to be {who} but asks for payment by {rail}. Real organisations never collect payment that way", who=who, rail=T(rail.replace('-', ' '))),
                                  ing.entities.rails[rail], "irreversible-payment"))
        if it.asks & {"share_code", "share_credentials"}:
            q = it.evidence.get("share_code") or it.evidence.get("share_credentials", "")
            it.mismatches.append((T("Claims to be {who} but asks you to share a code or password, which real organisations never ask for by message", who=who), q,
                                  "otp-credential-phish"))
        if "secrecy" in it.pressure_kinds:
            it.mismatches.append((T("Claims to be {who} but tells you to keep it secret", who=who), it.evidence.get("pressure:secrecy", ""), "authority-spoofing" if kind == "authority" else None))
    # A relative asking family for money is normal; what makes it a scam is a new number, secrecy, an emergency, a deadline or gift cards.
    suspicious_context = bool(it.pressure_kinds or ing.entities.rails or _NEW_NUMBER.search(ing.text))
    if kind == "relation" and "pay" in it.asks and suspicious_context:
        it.mismatches.append((T("Says it's family and asks for money, but gives you no way to check it's really them"),
                              it.evidence.get("pay", ""), "emotional-manipulation"))


SCENARIO_PURPOSE = {
    "prize-lottery": "claim-prize-reward", "claim-approved": "claim-prize-reward", "government-rebate": "claim-prize-reward", "inheritance-advance-fee": "claim-prize-reward",
    "ticket-prepay": "request-payment", "rental-deposit": "request-payment", "cheque-overpayment": "request-payment", "overpayment": "request-payment", "charity-appeal": "request-payment",
    "job-task": "offer-job-or-investment", "investment": "offer-job-or-investment",
    "account-verification": "urgent-account-warning", "bank-security": "urgent-account-warning", "tax-government": "urgent-account-warning", "utility-bill": "urgent-account-warning",
    "parcel-fee": "urgent-account-warning", "billing-update": "urgent-account-warning", "tech-support": "request-install-access",
    "family-emergency": "emotional-plea", "romance": "emotional-plea", "boss-gift-card": "emotional-plea",
    "subscription-renewal": "callback-request", "warranty-callback": "callback-request", "marketplace-code": "request-secret",
    "government-rebate": "claim-prize-reward", **ZH.SCENARIO_PURPOSE,
}


ALARM = Dual(r"\b(?:blocked|hacked|suspended|locked|compromised|unauthori[sz]ed|suspicious|fraudulent|deactivat\w+|disabled|limited|expir\w+|delayed|on hold|is full|storage (?:is )?full|storage limit|failed login|violation)\b", ZH.ALARM)
ACTION = Dual(r"\b(?:verify|verifying|reactivate|re-?activate|secure (?:it|your)|change (?:your )?password|open the app|click|tap|log ?in|sign in|renew now|track now|update (?:your )?(?:details|info|account)|confirm (?:your|identity)|act now|claim|call (?:us|now)|respond)\b", ZH.ACTION)


def classify_purpose(ing: Ingested, it: Intent) -> str:
    """Rule-based purpose from the closed catalogue. Purposes that ask the reader to give something up are checked first, in priority order."""
    pur = intents.PURPOSES
    risky = {
        "request-secret": bool(it.asks & {"share_code", "share_credentials"}) or it.scenario == "marketplace-code",
        "request-install-access": "install" in it.asks or bool(pur["request-install-access"].cues.search(ing.text) and it.scenario == "tech-support"),
        "request-payment": "pay" in it.asks or SCENARIO_PURPOSE.get(it.scenario) == "request-payment",
        "claim-prize-reward": SCENARIO_PURPOSE.get(it.scenario) == "claim-prize-reward",
        "offer-job-or-investment": SCENARIO_PURPOSE.get(it.scenario) == "offer-job-or-investment",
        "urgent-account-warning": (SCENARIO_PURPOSE.get(it.scenario) == "urgent-account-warning" or bool(it.pressure_kinds & {"threat"} and pur["urgent-account-warning"].cues.search(ing.text))
                                   or bool(ALARM.search(ing.text) and ACTION.search(ing.text))),  # the alarm form: a problem plus an instruction to act
        "emotional-plea": bool(it.pressure_kinds & {"emotional", "secrecy"}) or SCENARIO_PURPOSE.get(it.scenario) == "emotional-plea",
        "first-contact-opener": bool(it.opener),
        "callback-request": ("call" in it.asks and bool(ing.entities.phones)) or SCENARIO_PURPOSE.get(it.scenario) == "callback-request",
    }
    for pid in intents.PRIORITY_RISKY:
        if risky[pid]:
            return pid
    for pid in intents.PRIORITY_NORMAL:
        p = pur[pid]
        if pid == "social-chat":
            if len(ing.text) < 300 and not ing.entities.hosts and not ing.entities.rails:
                return pid
        elif p.cues is not None and p.cues.search(ing.text):
            return pid
    return "other"


def purpose_supported(pid: str, ing: Ingested, it: Intent) -> bool:
    """A purpose the MODEL chose is kept only if the message contains what that purpose needs (same idea as the tactic preconditions)."""
    if not intents.valid(pid):
        return False
    p = intents.PURPOSES[pid]
    if pid in ("other", "social-chat"):
        return True
    if pid == "request-payment":
        return "pay" in it.asks
    if pid == "request-secret":
        return bool(it.asks & {"share_code", "share_credentials"})
    if pid == "first-contact-opener":
        return bool(it.opener) or ("reply" in it.asks and not it.claimed)
    if pid == "callback-request":
        return "call" in it.asks and bool(ing.entities.phones)
    return bool(p.cues and p.cues.search(ing.text))


def _supported(ask: str, ing: Ingested) -> bool:
    """A model-added ask must be physically possible: no link in the message means nothing to click."""
    if ask == "click":
        return bool(ing.entities.hosts)
    if ask == "call":
        return bool(re.search(r"\bcall\b|\d{3}[\s.-]?\d{3,}", ing.text, re.I) or (CJK.search(ing.text) and Z(ZH.CALL_POSSIBLE).search(ing.text)))
    return True


CONSEQUENCE = Dual(r"\b(?:or|unless|otherwise|else|before)\b[^.!?]{0,70}\b(?:will|be|lose|cancel\w*|clos\w+|suspend\w*|block\w*|disconnect\w*|fine|penalt\w*|return\w*|delet\w+|arrest\w*|expire)\b", ZH.CONSEQUENCE)


def _pressure_supported(kind: str, ing: Ingested) -> bool:
    """A model-claimed pressure kind needs the text to back it. A bare time window ('expires in 15 minutes') is a fact, not pressure."""
    if PRESSURE_KINDS[kind].search(ing.text):
        return True
    return kind in ("deadline", "threat") and bool(CONSEQUENCE.search(ing.text))


def diagnose(ing: Ingested) -> Intent:
    it = _heuristic(ing)
    if llm.available():
        try:
            out = llm.chat_json(INTENT_SYSTEM, "MESSAGE:\n" + ing.redacted, heavy=False, purpose="intent")
            # The model can only ADD suspicion or fill gaps, never remove what the rules saw, and everything it adds is checked.
            it.asks |= {a for a in out.get("asks", []) if a in ASKS and _supported(a, ing)}
            kinds = out.get("pressure")
            kinds = [kinds] if isinstance(kinds, str) else (kinds or [])
            if kinds is True or out.get("pressure") is True:
                kinds = ["deadline"]
            it.pressure_kinds |= {k for k in kinds if k in PRESSURE_KINDS and _pressure_supported(k, ing)}
            ident = out.get("claimed_identity")
            name = str((ident.get("name") if isinstance(ident, dict) else ident) or "")[:60]
            if name and (not it.claimed or it.claimed in name.lower()) and (any(w in ing.text.lower() for w in re.findall(r"[a-z]{3,}", name.lower()))
                                                                          or (CJK.search(name) and canon(name) in canon(ing.text))):
                it.claimed = name.lower()  # only accepted if its words really appear in the message
                k = str(ident.get("kind", "")) if isinstance(ident, dict) else ""
                it.claimed_kind = k if k in ("authority", "organisation", "relation") else (it.claimed_kind or "organisation")
            mp = str(out.get("purpose") or "")
            if purpose_supported(mp, ing, it):
                it.model_purpose = mp
                if mp != it.purpose and intents.PURPOSES[mp].risk != intents.PURPOSES[it.purpose].risk and "other" not in (mp, it.purpose):
                    it.disagreements.append(f"rules read this as “{intents.PURPOSES[it.purpose].label}”, the model as “{intents.PURPOSES[mp].label}”")
            sc = str(out.get("scenario") or "")
            if sc in scenarios.SCENARIOS:
                if it.scenario and not scenarios.same_family(sc, it.scenario):
                    it.disagreements.append(f"rules see the “{scenarios.SCENARIOS[it.scenario].label}” script, the model sees “{scenarios.SCENARIOS[sc].label}”")
                elif not it.scenario:
                    it.model_scenario = sc
            it.used_ai = True
        except llm.LLMUnavailable:
            pass
    return it
