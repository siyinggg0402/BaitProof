"""Deterministic gates: grounding, verdict arbiter, flywheel. The model proposes; these decide."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.domain.schemas import TacticHit, Verdict

from .evidence import Ledger
from .intent import Intent
from .tools import Findings


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def grounding_gate(tactics: list[TacticHit], *texts: str) -> tuple[list[TacticHit], list[str]]:
    """Keep a tactic only if its quote really appears in the message. Kills hallucinated red flags."""
    hay = [_norm(t) for t in texts]
    kept, dropped, seen = [], [], set()
    for t in tactics:
        q = _norm(t.quote)
        if t.id in seen:
            continue
        if q and any(q in h for h in hay):
            kept.append(t)
            seen.add(t.id)
        else:
            dropped.append(t.id)
    return kept, dropped


@dataclass
class Decision:
    verdict: Verdict
    confidence: str  # high | medium | low
    reasons: list[str] = field(default_factory=list)
    model_dependent: bool = False  # True when the verdict/confidence rests on the model's opinion (a second look could change it)


def arbitrate(ledger: Ledger, intent: Intent, f: Findings, model_verdict: Verdict | None, injection: bool, english: bool = True) -> Decision:
    """Asymmetric by design: evidence can escalate freely; 'safe' must be earned and any disagreement downgrades it.
    Reads the ledger, so every verdict can name the evidence it rests on."""
    m_scam = model_verdict in (Verdict.SCAM, Verdict.LIKELY_SCAM)
    # Red-flag types from independent sources always count. Types only the model raised count only while the model is consistently
    # saying 'scam': a model that contradicts itself (or says safe/unsure) doesn't get to add flags.
    ind_ids = {e.tactic for e in ledger.independent_scam() if e.tactic}
    model_only = [t for t in ledger.tactic_ids() if t not in ind_ids]
    flags = len(ind_ids) + (len(model_only) if m_scam else 0) + (1 if ledger.has_script_match() else 0)  # a known scam script is itself a flag
    m_safe = model_verdict == Verdict.SAFE
    strong = ledger.strong_independent_scam()
    w, h = ledger.weight_independent("scam"), ledger.weight_independent("safe")  # stacked evidence, scam vs reassuring

    if strong:  # hard evidence from independent sources: the model can't talk us out of it
        d = Decision(Verdict.SCAM, "medium" if m_safe else "high", ["hard evidence: " + "; ".join(e.claim for e in strong[:2])], model_dependent=m_safe)
    elif not ind_ids and not ledger.has_script_match() and h > 0 and (m_scam or model_only):
        # Every red flag is the model's alone, and independent checks found reassuring facts: that is a doubt, not a verdict.
        d = Decision(Verdict.UNSURE, "low", ["only the AI is suspicious, and independent checks look reassuring"], model_dependent=True)
    elif flags >= 2 or w >= 4:  # two kinds of red flag, or enough smaller facts piling up
        conf = "low" if m_safe else ("high" if h < w / 2 else "medium")
        d = Decision(Verdict.SCAM if not m_safe else Verdict.LIKELY_SCAM, conf,
                     [f"{flags} separate red flags" if flags >= 2 else f"evidence adds up ({w:g} points against {h:g} reassuring)"],
                     model_dependent=m_safe or bool(model_only))
    elif flags == 1:
        d = Decision(Verdict.LIKELY_SCAM, "low" if (m_safe or h > w) else "medium", ["1 red flag" + (" (outweighed by reassuring facts)" if h > w else "")],
                     model_dependent=m_safe or bool(model_only))
    elif m_scam:
        d = Decision(Verdict.UNSURE, "low", ["model suspects a scam but gave no verifiable evidence"], model_dependent=True)
    elif intent.high_risk or f.suspicious_hosts or intent.pressure or injection or model_verdict == Verdict.UNSURE:
        d = Decision(Verdict.UNSURE, "low", ["asks for something sensitive or is hard to judge"])
    elif not english and not m_safe:
        d = Decision(Verdict.UNSURE, "low", ["can't judge this language with built-in rules alone"])
    elif "click" in intent.asks and not (f.all_links_official() or f.all_links_established()):
        d = Decision(Verdict.UNSURE, "low", ["contains a link that can't be verified"])
    else:
        d = Decision(Verdict.SAFE, "high" if m_safe else "medium", ["asks for nothing risky and no red flags found"], model_dependent=not m_safe)

    if injection and d.verdict == Verdict.SAFE:
        d = Decision(Verdict.UNSURE, "low", ["message tries to instruct the checker"])
    return d


def flywheel_gate(d: Decision, ledger: Ledger) -> tuple[bool, str]:
    """Only confident scam verdicts backed by NON-MODEL evidence may feed the training library, so neither a wrong
    label nor a model hallucination can be drilled as truth."""
    if d.verdict not in (Verdict.SCAM, Verdict.LIKELY_SCAM) or not ledger.tactic_ids():  # needs a tactic to drill
        return False, "not a confident scam: kept out of training"
    if d.confidence == "low":
        return False, "low confidence: kept out of training"
    if not ledger.has_independent_support():
        return False, "only the model suspects it (no independent evidence): kept out of training"
    return True, "added to training"


def output_gate(verdict: Verdict, tell: str, action: str, caveat: str) -> tuple[str, str, list[str]]:
    """Last gate before an answer leaves: enforce the safety/tone invariants and report what had to be repaired."""
    fixes: list[str] = []
    tell, action = " ".join(tell.split()), " ".join(action.split())
    if verdict == Verdict.SAFE and caveat not in action:
        action, fixes = (action + " " + caveat).strip(), fixes + ["added the 'verify first' caveat to a safe verdict"]
    if verdict != Verdict.SAFE and not action:
        action, fixes = "Don't act on it yet. Check using a phone number or website you already trust.", fixes + ["supplied a safe action"]
    if not tell:
        tell, fixes = "I can't point to one clear giveaway, so treat it with care.", fixes + ["supplied a giveaway line"]
    if verdict in (Verdict.SCAM, Verdict.LIKELY_SCAM) and re.search(r"\b(?:it is|this is) (?:definitely )?(?:safe|fine|legit)\b", action, re.I):
        action, fixes = "Don't act on it. Check using a phone number or website you already trust.", fixes + ["removed reassurance that contradicted a scam verdict"]
    return tell[:400], action[:500], fixes
