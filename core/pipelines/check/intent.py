"""Stage 2, intent diagnosis: what is the sender asking the reader to DO, under what pressure, as whom?
Scams ask for an action under pressure; legitimate messages mostly inform. This is the main discriminator."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.ai import llm
from core.ai.prompts import INTENT_SYSTEM

from .ingest import Ingested
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
RELATIONS = re.compile(r"\b(mum|mom|dad|grandma|grandpa|son|daughter|grandson|granddaughter)\b", re.I)


@dataclass
class Intent:
    asks: set[str] = field(default_factory=set)
    pressure: bool = False
    claimed: str = ""
    evidence: dict[str, str] = field(default_factory=dict)  # ask -> quoted text
    used_ai: bool = False

    @property
    def high_risk(self) -> set[str]:
        return self.asks & HIGH_RISK_ASKS

    def summary(self) -> str:
        return f"asks={sorted(self.asks) or 'nothing'}; pressure={self.pressure}; claims_to_be={self.claimed or 'unknown'}"


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
    pm = PRESSURE_RE.search(ing.text)
    it.pressure = bool(pm)
    if pm:
        it.evidence["pressure"] = pm.group(0)[:80]
    rel = RELATIONS.search(ing.text)
    it.claimed = ing.entities.brands[0] if ing.entities.brands else (rel.group(1).lower() if rel else "")
    return it


def diagnose(ing: Ingested) -> Intent:
    it = _heuristic(ing)
    if llm.available():
        try:
            out = llm.chat_json(INTENT_SYSTEM, "MESSAGE:\n" + ing.redacted, heavy=False)
            # Union, never replace: a model can only ADD suspicion, not remove what the rules saw.
            it.asks |= {a for a in out.get("asks", []) if a in ASKS}
            it.pressure = it.pressure or bool(out.get("pressure"))
            it.claimed = it.claimed or str(out.get("claimed_identity") or "")[:60]
            it.used_ai = True
        except llm.LLMUnavailable:
            pass
    return it
