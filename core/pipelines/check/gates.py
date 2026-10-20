"""Deterministic gates: grounding, verdict arbiter, flywheel. The model proposes; these decide."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.domain import intents
from core.domain.i18n import tr
from core.domain.lang import Dual, canon
from core.domain.schemas import TacticHit, Verdict

from .evidence import Ledger
from .intent import Intent
from .tools import Findings


def _norm(s: str) -> str:
    return canon(s)  # width-folded, lower-case, Traditional folded to Simplified, spacing ignored for Chinese


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


def arbitrate(ledger: Ledger, intent: Intent, f: Findings, model_verdict: Verdict | None, injection: bool, english: bool = True, scam_votes: int = 0, lang: str = "en") -> Decision:
    """Asymmetric by design: evidence can escalate freely; 'safe' must be earned and any disagreement downgrades it.
    Reads the ledger, so every verdict can name the evidence it rests on."""
    T = lambda s, **kw: tr(s, lang, **kw)  # noqa: E731  (the reasons are shown to the user in their language)
    m_scam = model_verdict in (Verdict.SCAM, Verdict.LIKELY_SCAM)
    # A purpose that asks the reader to give something up (money, a code, a click-through to 'verify', a call), supported by the text, is
    # never cleared on its own: a genuine one exists (a relative asking for a loan) but 'safe' is the wrong answer for it.
    risky_purpose = any(intents.PURPOSES[p].risk == "risky" for p in (intent.purpose, intent.model_purpose) if p in intents.PURPOSES)
    w, h = ledger.weight_independent("scam"), ledger.weight_independent("safe")  # stacked evidence, scam vs reassuring
    # Red-flag types from independent sources always count. Types only the model raised count only while the model is consistently
    # saying 'scam': a model that contradicts itself (or says safe/unsure) doesn't get to add flags.
    ind_ids = {e.tactic for e in ledger.independent_scam() if e.tactic and e.strength != "weak"}  # weak evidence adds weight, never a flag by itself
    model_only = [t for t in ledger.tactic_ids() if t not in ind_ids]
    ind_flag = bool(ind_ids) or w >= 2  # independent evidence of at least medium weight counts as a red flag even without a named trick
    flags = (len(ind_ids) or (1 if w >= 2 else 0)) + (len(model_only) if m_scam else 0) + (1 if ledger.has_script_match() else 0)  # a known scam script is itself a flag
    m_safe = model_verdict == Verdict.SAFE
    strong = ledger.strong_independent_scam()

    if strong:  # hard evidence from independent sources: the model can't talk us out of it
        d = Decision(Verdict.SCAM, "medium" if m_safe else "high", [T("hard evidence: {facts}", facts="; ".join(e.claim for e in strong[:2]))], model_dependent=m_safe)
    elif not ind_flag and not ledger.has_script_match() and (m_scam or model_only) and (h > 0 or not intent.asks):
        # Every red flag is the model's alone, and either independent checks found reassuring facts or the message asks for nothing
        # (nothing to steal): that is a doubt, not a verdict.
        why = T("independent checks look reassuring") if h > 0 else T("the message asks for nothing")
        d = Decision(Verdict.UNSURE, "low", [T("only the AI is suspicious, and {why}", why=why)], model_dependent=True)
    elif flags >= 2 or w >= 4:  # two kinds of red flag, or enough smaller facts piling up
        conf = "low" if m_safe else ("high" if h < w / 2 else "medium")
        d = Decision(Verdict.SCAM if not m_safe else Verdict.LIKELY_SCAM, conf,
                     [T("{n} separate red flags", n=flags) if flags >= 2 else T("evidence adds up ({w:g} points against {h:g} reassuring)", w=w, h=h)],
                     model_dependent=m_safe or bool(model_only))
    elif not ind_flag and not ledger.has_script_match() and model_only and scam_votes < 2:
        # A red flag only the model raised, seen once: not enough for 'likely scam'. A second consistent look (the loop's job) is.
        d = Decision(Verdict.UNSURE, "low", [T("only the AI raised a red flag, and only once so far")], model_dependent=True)
    elif flags == 1:
        d = Decision(Verdict.LIKELY_SCAM, "low" if (m_safe or h > w) else "medium", [T("1 red flag (outweighed by reassuring facts)") if h > w else T("1 red flag")],
                     model_dependent=m_safe or bool(model_only))
    elif m_scam:
        d = Decision(Verdict.UNSURE, "low", [T("model suspects a scam but gave no verifiable evidence")], model_dependent=True)
    elif intent.high_risk or f.suspicious_hosts or intent.pressure or injection or intent.opener or risky_purpose or model_verdict == Verdict.UNSURE:
        only_model = not (intent.high_risk or f.suspicious_hosts or intent.pressure or injection or intent.opener or risky_purpose)  # a second look can only help here
        d = Decision(Verdict.UNSURE, "low", [T("the AI isn't sure and nothing else explains it") if only_model else T("asks for something sensitive or is hard to judge")],
                     model_dependent=only_model)
    elif not english and not m_safe:
        d = Decision(Verdict.UNSURE, "low", [T("can't judge this language with built-in rules alone")])
    elif "click" in intent.asks and not (f.all_links_official() or f.all_links_established()):
        d = Decision(Verdict.UNSURE, "low", [T("contains a link that can't be verified")])
    elif model_verdict is None and not any(e.kind != "model" and e.source != "benign-intent" for e in ledger.safe()):
        # No model opinion (outage, or not configured) and no tool positively verified anything: the rules alone can't vouch for a message.
        d = Decision(Verdict.UNSURE, "low", [T("built-in rules alone can't vouch that a message is safe")])
    else:
        # Every independent check is clean. A model 'safe' makes that high confidence. (A model that is only 'unsure' never reaches here:
        # the loop's second look can turn 'unsure' into 'safe', and two unsure looks stay unsure.)
        d = Decision(Verdict.SAFE, "high" if m_safe else "medium", [T("asks for nothing risky and no red flags found")], model_dependent=not m_safe)

    if d.verdict == Verdict.SCAM and not ledger.has_independent_support():  # the strongest label needs evidence the model didn't supply
        d = Decision(Verdict.LIKELY_SCAM, "medium" if d.confidence == "high" else d.confidence, d.reasons + [T("only the AI raised these flags, so 'likely' rather than 'scam'")],
                     model_dependent=True)

    if d.verdict == Verdict.SAFE and not english:
        # Our rules cannot read this language, so nothing independent has checked the message: a model's "safe" stands alone. Measured on
        # machine-translated SMS (Indonesian, Japanese, Korean, Hindi, Arabic) that let 1-2 scams in 40 through, so "safe" is withheld.
        d = Decision(Verdict.UNSURE, "low", [T("can't fully check this language with built-in rules, so I can't call it safe")])

    if injection and d.verdict == Verdict.SAFE:
        d = Decision(Verdict.UNSURE, "low", [T("message tries to instruct the checker")])
    return d


def flywheel_gate(d: Decision, ledger: Ledger, lang: str = "en") -> tuple[bool, str]:
    """Only confident scam verdicts backed by NON-MODEL evidence may feed the training library, so neither a wrong
    label nor a model hallucination can be drilled as truth."""
    if d.verdict not in (Verdict.SCAM, Verdict.LIKELY_SCAM) or not ledger.tactic_ids():  # needs a tactic to drill
        return False, tr("not a confident scam: kept out of training", lang)
    if d.confidence == "low":
        return False, tr("low confidence: kept out of training", lang)
    if not ledger.has_independent_support():
        return False, tr("only the model suspects it (no independent evidence): kept out of training", lang)
    return True, tr("added to training", lang)


_REASSURING = Dual(r"\b(?:it is|this is) (?:definitely )?(?:safe|fine|legit)\b", r"(?:这|它|此)(?:条|个)?(?:消息|短信|信息|邮件)?(?:是|很|完全|绝对)?(?:安全|正常|可靠|没问题)(?:的)?|可以放心|不用担心|请放心")


def output_gate(verdict: Verdict, tell: str, action: str, caveat: str, lang: str = "en") -> tuple[str, str, list[str]]:
    """Last gate before an answer leaves: enforce the safety/tone invariants and report what had to be repaired."""
    T = lambda s: tr(s, lang)  # noqa: E731
    fixes: list[str] = []
    tell, action = " ".join(tell.split()), " ".join(action.split())
    if verdict == Verdict.SAFE and caveat not in action:
        action, fixes = (action + " " + caveat).strip(), fixes + [T("added the 'verify first' caveat to a safe verdict")]
    if verdict != Verdict.SAFE and not action:
        action, fixes = T("Don't act on it yet. Check using a phone number or website you already trust."), fixes + [T("supplied a safe action")]
    if not tell:
        tell, fixes = T("I can't point to one clear giveaway, so treat it with care."), fixes + [T("supplied a giveaway line")]
    if verdict in (Verdict.SCAM, Verdict.LIKELY_SCAM) and _REASSURING.search(action):
        action, fixes = T("Don't act on it. Check using a phone number or website you already trust."), fixes + [T("removed reassurance that contradicted a scam verdict")]
    return tell[:400], action[:500], fixes
