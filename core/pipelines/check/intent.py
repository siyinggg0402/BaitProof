"""Stage 2, intent diagnosis: what is the sender asking the reader to DO, under what pressure, as whom?
Scams ask for an action under pressure; legitimate messages mostly inform. This is the main discriminator."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.ai import llm
from core.ai.prompts import INTENT_SYSTEM

from .ingest import Ingested
from . import scenarios
from .knowledge import C, PRESSURE_RE

ASKS = ("pay", "share_code", "share_credentials", "install", "click", "call", "reply")
HIGH_RISK_ASKS = {"pay", "share_code", "share_credentials", "install"}

ASK_RULES = {
    "pay": C(r"\b(?:pay|send|transfer|wire|deposit|top up|buy|move)\b[^.!?\n]{0,40}(?:[$€£]|\d+ ?(?:dollars|usd|eur)|\bfee\b|\btax\b|gift ?cards?|bitcoin|crypto|usdt|voucher|balance|savings|money|cash)|\bpag(?:ue|ar)\b|\b(?:send|return|refund|pay|transfer) (?:it|that|the money|the funds|them) back\b"),
    "share_code": C(r"\b(?:reply|send|read|share|give|forward|tell)\b[^.!?\n]{0,25}\b(?:code|otp|pin)\b|\bread (?:it|them) (?:out )?to me\b"),
    "share_credentials": C(r"\b(?:enter|confirm|verify|provide|share|give|send|need|require|ask(?:ed)? for)\s+(?:only |just )?(?:us |me )?(?:your |the )?(?:password|pin|ssn|social security number|card number|medicare number|date of birth|bank details|login)"),
    "install": C(r"\binstall\b|\bdownload (?:the |this )?(?:app|software)\b"),
    "click": C(r"\b(?:click|tap|open)\b[^.!?\n]{0,15}\b(?:link|here)\b"),
    "call": C(r"\bcall\b"),
    "reply": C(r"\breply\b|\brespond\b"),
}
NEGATION = re.compile(r"\b(?:never|don'?t|do not|won'?t|will not)\b[^.!?]{0,25}$", re.I)
RELATIONS = re.compile(r"\b(mum|mom|dad|grandma|grandpa|nan|nana|gran|son|daughter|grandson|granddaughter|it'?s me)\b", re.I)
AUTHORITY = re.compile(r"\b(officer|detective|police|irs|hmrc|social security|court|tax office|government|cyber ?crime|fraud department|security team)\b", re.I)
ORGANISATION = re.compile(r"\b(bank|microsoft|apple|amazon|paypal|netflix|your provider|support team|customer service)\b", re.I)

PRESSURE_KINDS = {
    "deadline": PRESSURE_RE,
    "threat": C(r"\b(?:arrest\w*|warrant|court|legal action|lawsuit|account (?:will be )?(?:closed|suspended|blocked|deactivated)|disconnect\w*|detain\w*|penalty|lose access)\b"),
    "secrecy": C(r"\b(?:don'?t tell|do not tell|keep (?:this|it) (?:a )?secret|between us|do not (?:speak|talk) to|don'?t call|please don'?t call)\b"),
    "emotional": C(r"\b(?:emergency|hospital|in trouble|stuck|please hurry|i love you|lonely|bail|accident)\b"),
}


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
    used_ai: bool = False

    @property
    def pressure(self) -> bool:
        return bool(self.pressure_kinds)

    @property
    def high_risk(self) -> set[str]:
        return self.asks & HIGH_RISK_ASKS

    def summary(self) -> str:
        who = f"{self.claimed} ({self.claimed_kind})" if self.claimed else "unknown"
        sc = f"; follows_script={self.scenario}" if self.scenario else ""
        return f"asks={sorted(self.asks) or 'nothing'}; pressure={sorted(self.pressure_kinds) or 'none'}; claims_to_be={who}{sc}"


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
    if ing.entities.rails and "pay" not in it.asks and re.search(r"\b(?:buy|send|pay)\b", ing.text, re.I):
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
        if m:
            it.claimed, it.claimed_kind = m.group(0).lower(), kind
            it.evidence["identity"] = m.group(0)
            break
    it.scenario, it.scenario_signs, q = scenarios.detect(ing.text)
    if it.scenario:
        it.evidence["scenario"] = q
    _mismatches(it, ing)
    return it


def _mismatches(it: Intent, ing: Ingested) -> None:
    """Claim-vs-ask contradictions: the pattern real senders almost never produce."""
    who, kind = it.claimed, it.claimed_kind
    if kind in ("authority", "organisation"):
        if ing.entities.rails:
            rail = next(iter(ing.entities.rails))
            it.mismatches.append((f"Claims to be {who} but asks for payment by {rail.replace('-', ' ')}. Real organisations never collect payment that way",
                                  ing.entities.rails[rail], "irreversible-payment"))
        if it.asks & {"share_code", "share_credentials"}:
            q = it.evidence.get("share_code") or it.evidence.get("share_credentials", "")
            it.mismatches.append((f"Claims to be {who} but asks you to share a code or password, which real organisations never ask for by message", q,
                                  "otp-credential-phish"))
        if "secrecy" in it.pressure_kinds:
            it.mismatches.append((f"Claims to be {who} but tells you to keep it secret", it.evidence.get("pressure:secrecy", ""), "authority-spoofing" if kind == "authority" else None))
    # A relative asking family for money is normal; what makes it a scam is a new number, secrecy, an emergency, a deadline or gift cards.
    suspicious_context = bool(it.pressure_kinds or ing.entities.rails or re.search(r"\b(?:new (?:number|phone)|lost my|dropped my phone)\b", ing.text, re.I))
    if kind == "relation" and "pay" in it.asks and suspicious_context:
        it.mismatches.append(("Says it's family and asks for money, but gives you no way to check it's really them",
                              it.evidence.get("pay", ""), "emotional-manipulation"))


def _supported(ask: str, ing: Ingested) -> bool:
    """A model-added ask must be physically possible: no link in the message means nothing to click."""
    if ask == "click":
        return bool(ing.entities.hosts)
    if ask == "call":
        return bool(re.search(r"\bcall\b|\d{3}[\s.-]?\d{3,}", ing.text, re.I))
    return True


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
            it.pressure_kinds |= {k for k in kinds if k in PRESSURE_KINDS}
            ident = out.get("claimed_identity")
            name = str((ident.get("name") if isinstance(ident, dict) else ident) or "")[:60]
            if name and (not it.claimed or it.claimed in name.lower()) and any(w in ing.text.lower() for w in re.findall(r"[a-z]{3,}", name.lower())):
                it.claimed = name.lower()  # only accepted if its words really appear in the message
                k = str(ident.get("kind", "")) if isinstance(ident, dict) else ""
                it.claimed_kind = k if k in ("authority", "organisation", "relation") else (it.claimed_kind or "organisation")
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
