"""Check pipeline (PLAN §6a): ingest -> victim triage -> intent -> tools -> analysis -> grounding -> arbiter
-> critic -> compose -> flywheel gate. Each gate writes to the trace."""
from __future__ import annotations

from core.domain.schemas import CheckResult, TacticHit, Verdict
from core.domain.tactics import TACTICS
from core.storage import library, model

from . import analysis, gates, intent as intent_stage, tools
from .ingest import ingest
from .trace import Trace

CAVEAT = "This looks okay, but I can't be sure. If it asks for money, codes or a rush, check first using an official number or website you already trust."

HEADLINES = {
    Verdict.SCAM: "🚨 SCAM. Don't pay, don't tap the link.",
    Verdict.LIKELY_SCAM: "⚠️ Likely a scam. Don't act on it yet.",
    Verdict.SAFE: "✅ Looks safe, but verify first.",
    Verdict.UNSURE: "❓ Not sure. Treat it with care.",
    Verdict.VICTIM: "💛 You're not alone, and this is not your fault.",
}


def check_message(text: str, store: bool = True) -> CheckResult:
    tr = Trace()
    ing = ingest(text)
    tr.add("ingest", "flag" if ing.injection else "pass",
           "message tries to give the checker instructions" if ing.injection else f"{len(ing.entities.hosts)} link(s), {len(ing.entities.rails)} payment method(s) found")

    if ing.victim:
        tr.add("triage", "flag", "sounds like you may already have acted: switching to support")
        return CheckResult(
            verdict=Verdict.VICTIM, headline=HEADLINES[Verdict.VICTIM],
            tell="Scammers are skilled, and many smart people get fooled.",
            action="Call your bank or card company now and tell them. Change any password you shared. Report it to your local police or consumer-fraud line. Tell someone you trust.",
            trace=tr.steps)

    it = intent_stage.diagnose(ing)
    tr.add("intent", "flag" if it.high_risk or it.pressure else "pass", it.summary())

    f = tools.run_tools(ing, tr)

    proposed = analysis.rule_tactics(ing, it, f)
    out = analysis.model_analysis(ing, it, f)
    m_verdict = None
    tell = action = abstract = phrase = ""
    if out:
        m_verdict, m_tactics = analysis.parse_model(out)
        proposed += m_tactics
        tell, action = str(out.get("the_tell", ""))[:400], str(out.get("action", ""))[:400]
        abstract, phrase = str(out.get("abstract_example", "")), str(out.get("tell_phrase", ""))
        tr.add("analysis", "pass", f"model says {m_verdict.value}; {len(m_tactics)} tactic(s) proposed")
    else:
        tr.add("analysis", "skip", "no AI configured: using built-in rules only")

    tactics, dropped = gates.grounding_gate(proposed, ing.text, ing.redacted)
    tr.add("grounding", "flag" if dropped else "pass",
           f"dropped {len(dropped)} claim(s) with no matching words in the message" if dropped else f"{len(tactics)} red flag(s) verified against the message")

    d = gates.arbitrate(tactics, it, f, m_verdict, ing.injection, ing.english)
    tr.add("arbiter", "pass", f"{d.verdict.value} ({d.confidence} confidence): " + "; ".join(d.reasons))

    if d.verdict == Verdict.SAFE and out:
        concern = analysis.critic(ing, it)
        if concern:
            d = gates.Decision(Verdict.UNSURE, "low", [f"second opinion: {concern}"])
            tr.add("critic", "flag", concern)
        else:
            tr.add("critic", "pass", "second reviewer found nothing")

    verdict, first = d.verdict, (tactics[0].id if tactics else None)
    if not tell and first:
        tell = (f"“{tactics[0].quote}”: " if tactics[0].quote else "") + TACTICS[first]["tell"]
    if not action:
        action = TACTICS[first]["action"] if first and verdict != Verdict.SAFE else CAVEAT
    if verdict == Verdict.SAFE and action != CAVEAT:
        action += " " + CAVEAT
    if verdict == Verdict.UNSURE and not tell:
        tell = "I can't find a clear giveaway, but I can't rule a scam out either."

    ok, why = gates.flywheel_gate(d, tactics)
    added: list[str] = []
    if ok and store:
        ids = [t.id for t in tactics]
        phrase = phrase or tactics[0].quote
        # Prefer the model's name-free rewrite; otherwise the deterministic scrub (names can slip through offline).
        library.add_user_example(abstract or ing.text, ids, phrase, tell, action)
        model.record_exposure(ids)
        added = ids
    tr.add("flywheel", "pass" if added else "skip", why)

    return CheckResult(verdict=verdict, headline=HEADLINES[verdict], tell=tell, action=action, tactics=tactics,
                       added_to_training=added, evidence=f.web_notes, used_ai=bool(out), confidence=d.confidence, trace=tr.steps)
