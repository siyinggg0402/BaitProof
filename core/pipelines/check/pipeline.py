"""Check pipeline (PLAN §6a): ingest -> victim triage -> intent -> tools -> analysis -> grounding -> arbiter
-> critic -> compose -> flywheel gate. Each gate writes to the trace."""
from __future__ import annotations

import os

from core import obs
from core.ai import llm
from core.domain.schemas import CheckResult, TacticHit, Verdict
from core.domain.tactics import TACTICS
from core.obs.logger import fingerprint
from core.obs.metrics import cost_usd
from core.storage import library, model

from . import analysis, gates, intent as intent_stage, tools
from .evidence import Ledger
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


def check_message(text: str, store: bool = True, on_event=None, log: bool = True) -> CheckResult:
    """Run one check. Never crashes on internal errors (returns a cautious 'not sure'), always logs one structured event."""
    run = obs.start()
    tr = Trace(on_event)
    try:
        result = _check(text, store, tr, run)
    except ValueError:
        raise  # invalid input (empty message): the caller reports it
    except Exception as e:
        obs.emit({"kind": "error", "where": "check", "type": type(e).__name__, "id": run.id})
        tr.add("guard", "block", "internal error: returning a cautious answer")
        result = CheckResult(verdict=Verdict.UNSURE, headline=HEADLINES[Verdict.UNSURE], confidence="low",
                             tell="I couldn't finish checking this message.", action=CAVEAT.replace("This looks okay, but I", "I"), trace=tr.steps)
    result.check_id = run.id
    if log:
        _log(text, result, run)
    return result


def _log(text: str, r: CheckResult, run: obs.Run) -> None:
    tot = run.llm_totals()
    obs.emit({
        "kind": "check", "id": run.id, "verdict": r.verdict.value, "confidence": r.confidence, "rounds": run.rounds,
        "latency_ms": run.elapsed_ms, "ai_configured": llm.available(), "used_ai": r.used_ai, "model": os.getenv("NEBIUS_MODEL", ""),
        "msg": {"fp": fingerprint(text), "len": len(text), **run.meta},
        "stages": [{"stage": s.stage, "status": s.status, "ms": s.ms} for s in r.trace],
        "evidence": run.meta.pop("evidence", []), "tools": run.tools, "llm": run.llm, "llm_calls": tot["calls"], "tokens_in": tot["tokens_in"], "tokens_out": tot["tokens_out"],
        "cost_usd": round(cost_usd(tot["tokens_in"], tot["tokens_out"]), 6), "flywheel": bool(r.added_to_training),
    })


def _check(text: str, store: bool, tr: Trace, run: obs.Run) -> CheckResult:
    ing = ingest(text)
    run.meta["english"] = ing.english
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

    ledger = Ledger()
    analysis.rule_evidence(ing, it, f, ledger)
    out = analysis.model_analysis(ing, it, f)
    m_verdict = None
    tell = action = abstract = phrase = ""
    if out:
        m_verdict, m_tactics = analysis.parse_model(out)
        kept, dropped = gates.grounding_gate(m_tactics, ing.text, ing.redacted)  # model claims must quote the message
        for t in kept:
            ledger.add("model", "analysis", "scam", "medium", t.why or f"The AI reviewer spotted: {TACTICS[t.id]['label'].lower()}", t.quote, t.id)
        if m_verdict == Verdict.SAFE:
            ledger.add("model", "analysis", "safe", "medium", "The AI reviewer found nothing suspicious")
        tell, action = str(out.get("the_tell", ""))[:400], str(out.get("action", ""))[:400]
        abstract, phrase = str(out.get("abstract_example", "")), str(out.get("tell_phrase", ""))
        tr.add("analysis", "pass", f"model says {m_verdict.value}; {len(m_tactics)} tactic(s) proposed")
        tr.add("grounding", "flag" if dropped else "pass",
               f"dropped {len(dropped)} AI claim(s) with no matching words in the message" if dropped else f"{len(kept)} AI claim(s) verified against the message")
    else:
        tr.add("analysis", "skip", "no AI configured: using built-in rules only")
        tr.add("grounding", "pass", f"{len(ledger.tactic_ids())} red flag(s) from built-in rules")
    analysis.safe_evidence(ing, it, ledger)

    d = gates.arbitrate(ledger, it, f, m_verdict, ing.injection, ing.english)
    tr.add("arbiter", "pass", f"{d.verdict.value} ({d.confidence} confidence): " + "; ".join(d.reasons))

    if d.verdict == Verdict.SAFE and out:
        concern = analysis.critic(ing, it)
        if concern:
            d = gates.Decision(Verdict.UNSURE, "low", [f"second opinion: {concern}"])
            ledger.add("model", "critic", "scam", "weak", f"A second reviewer was worried: {concern}")
            tr.add("critic", "flag", concern)
        else:
            ledger.add("model", "critic", "safe", "weak", "A second reviewer looked for risk signals and found none")
            tr.add("critic", "pass", "second reviewer found nothing")

    tactics = ledger.tactic_hits()
    verdict, first = d.verdict, (tactics[0].id if tactics else None)
    if not tell and first:
        tell = (f"“{tactics[0].quote}”: " if tactics[0].quote else "") + TACTICS[first]["tell"]
    if not action:
        action = TACTICS[first]["action"] if first and verdict != Verdict.SAFE else CAVEAT
    if verdict == Verdict.SAFE and action != CAVEAT:
        action += " " + CAVEAT
    if verdict == Verdict.UNSURE and not tell:
        tell = "I can't find a clear giveaway, but I can't rule a scam out either."

    ok, why = gates.flywheel_gate(d, ledger)
    added: list[str] = []
    if ok and store:
        ids = ledger.tactic_ids()
        phrase = phrase or tactics[0].quote
        # Prefer the model's name-free rewrite; otherwise the deterministic scrub (names can slip through offline).
        library.add_user_example(abstract or ing.text, ids, phrase, tell, action)
        model.record_exposure(ids)
        added = ids
    tr.add("flywheel", "pass" if added else "skip", why)

    run.meta["evidence"] = [{"kind": e.kind, "source": e.source, "supports": e.supports, "strength": e.strength, "tactic": e.tactic} for e in ledger.items]
    return CheckResult(verdict=verdict, headline=HEADLINES[verdict], tell=tell, action=action, tactics=tactics,
                       added_to_training=added, evidence=ledger.items, used_ai=bool(out), confidence=d.confidence, trace=tr.steps)
