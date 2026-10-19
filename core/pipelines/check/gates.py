"""Deterministic gates: grounding, verdict arbiter, flywheel. The model proposes; these decide."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.domain.schemas import TacticHit, Verdict

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


def arbitrate(tactics: list[TacticHit], intent: Intent, f: Findings, model_verdict: Verdict | None, injection: bool, english: bool = True) -> Decision:
    """Asymmetric by design: evidence can escalate freely; 'safe' must be earned and any disagreement downgrades it."""
    ids = {t.id for t in tactics}
    m_scam = model_verdict in (Verdict.SCAM, Verdict.LIKELY_SCAM)
    m_safe = model_verdict == Verdict.SAFE
    why: list[str] = []

    hard = (
        bool(f.hard_hosts) or bool(ids & {"irreversible-payment", "remote-access-request"})
        or ("pay" in intent.asks and intent.pressure)
        or ("share_code" in intent.asks and "otp-credential-phish" in ids)
    )
    if hard:
        why.append("hard evidence: " + ", ".join(sorted(ids & {"irreversible-payment", "remote-access-request", "otp-credential-phish", "lookalike-link"})
                                                  or (["asks for payment under pressure"] if "pay" in intent.asks else ["impersonating link"])))
        d = Decision(Verdict.SCAM, "medium" if m_safe else "high", why)
    elif len(ids) >= 2:
        d = Decision(Verdict.SCAM if not m_safe else Verdict.LIKELY_SCAM, "low" if m_safe else "high", [f"{len(ids)} grounded red flags"])
    elif len(ids) == 1:
        d = Decision(Verdict.LIKELY_SCAM, "low" if m_safe else "medium", ["1 grounded red flag"])
    elif m_scam:
        d = Decision(Verdict.UNSURE, "low", ["model suspects a scam but gave no verifiable evidence"])
    elif intent.high_risk or f.suspicious_hosts or intent.pressure or injection or model_verdict == Verdict.UNSURE:
        d = Decision(Verdict.UNSURE, "low", ["asks for something sensitive or is hard to judge"])
    elif not english and not m_safe:
        d = Decision(Verdict.UNSURE, "low", ["can't judge this language with built-in rules alone"])
    elif "click" in intent.asks:
        d = Decision(Verdict.UNSURE, "low", ["contains a link that can't be verified"])
    else:
        d = Decision(Verdict.SAFE, "high" if m_safe else "medium", ["asks for nothing risky and no red flags found"])

    if injection and d.verdict == Verdict.SAFE:
        d = Decision(Verdict.UNSURE, "low", ["message tries to instruct the checker"])
    return d


def flywheel_gate(d: Decision, tactics: list[TacticHit]) -> tuple[bool, str]:
    """Only confident scam verdicts may feed the training library, so a wrong label can't be drilled as truth."""
    if d.verdict not in (Verdict.SCAM, Verdict.LIKELY_SCAM) or not tactics:
        return False, "not a confident scam: kept out of training"
    if d.confidence == "low":
        return False, "low confidence: kept out of training"
    return True, "added to training"
