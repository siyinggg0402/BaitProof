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

from . import analysis, engine, gates, intent as intent_stage
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
        "evidence": run.meta.pop("evidence", []), "tools": run.tools, "llm": run.llm, "llm_calls": tot["calls"], "tokens_in": tot["tokens_in"], "tokens_out": tot["tokens_out"], "pii_scrubbed": sum(c.get("pii_scrubbed", 0) for c in run.llm),
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

    case = engine.investigate(ing, it, tr, run)  # first pass, then loops until confident or out of budget
    ledger, d, out, f = case.ledger, case.decision, case.out, case.f
    tell = str(out.get("the_tell", ""))[:400] if out else ""
    action = str(out.get("action", ""))[:400] if out else ""
    abstract, phrase = (str(out.get("abstract_example", "")), str(out.get("tell_phrase", ""))) if out else ("", "")

    if d.verdict == Verdict.SAFE and case.votes:
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
    if verdict == Verdict.SAFE and not tell:
        tell = "Nothing here asks for money, codes, passwords or a rush, and I found no red flags."
    tell, action, fixes = gates.output_gate(verdict, tell, action, CAVEAT)
    tr.add("output", "flag" if fixes else "pass", "; ".join(fixes) if fixes else "tone and safety rules satisfied")

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
                       added_to_training=added, evidence=ledger.items, used_ai=bool(case.votes), confidence=d.confidence, trace=tr.steps)
