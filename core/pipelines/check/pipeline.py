"""Check pipeline (PLAN §6a): ingest -> victim triage -> intent -> tools -> analysis -> grounding -> arbiter
-> critic -> compose -> flywheel gate. Each gate writes to the trace."""
from __future__ import annotations

import os

from core import obs
from core.ai import llm
from core.domain import i18n
from core.domain.i18n import tactic_text, tr
from core.domain.lang import detect
from core.domain.schemas import CheckResult, Verdict
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


def reply_language(text: str, lang: str | None) -> str:
    """The language to answer in: the user's choice if they made one, otherwise the message's own language (English if we can't tell)."""
    if lang:
        return i18n.norm(lang)
    d = detect(text) if text.strip() else "en"
    return d if d in ("zh", "zh-Hant") else "en"


def check_message(text: str, store: bool = True, on_event=None, log: bool = True, lang: str | None = None) -> CheckResult:
    """Run one check. Never crashes on internal errors (returns a cautious 'not sure'), always logs one structured event.
    `lang` is the language to answer in (en | zh | zh-Hant); by default the message's own."""
    run = obs.start()
    reply = reply_language(text, lang)
    trace = Trace(on_event, reply)
    try:
        result = _check(text, store, trace, run, reply)
    except ValueError:
        raise  # invalid input (empty message): the caller reports it
    except Exception as e:
        obs.emit({"kind": "error", "where": "check", "type": type(e).__name__, "id": run.id})
        trace.add("guard", "block", "internal error: returning a cautious answer")
        result = CheckResult(verdict=Verdict.UNSURE, headline=tr(HEADLINES[Verdict.UNSURE], reply), confidence="low", lang=reply,
                             tell=tr("I couldn't finish checking this message.", reply),
                             action=tr("I can't be sure. If it asks for money, codes or a rush, check first using an official number or website you already trust.", reply), trace=trace.steps)
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


def _check(text: str, store: bool, tr_: Trace, run: obs.Run, reply: str = "en") -> CheckResult:
    ing = ingest(text)
    ing.reply = reply
    run.meta["english"] = ing.english
    run.meta["lang"] = ing.lang
    T = lambda s, **kw: tr(s, reply, **kw)  # noqa: E731
    tr_.add("ingest", "flag" if ing.injection else "pass",
            "message tries to give the checker instructions" if ing.injection else "{n} link(s), {m} payment method(s) found", n=len(ing.entities.hosts), m=len(ing.entities.rails))

    if ing.victim:
        tr_.add("triage", "flag", "sounds like you may already have acted: switching to support")
        return CheckResult(
            verdict=Verdict.VICTIM, headline=T(HEADLINES[Verdict.VICTIM]),
            tell=T("Scammers are skilled, and many smart people get fooled."),
            action=T("Call your bank or card company now and tell them. Change any password you shared. Report it to your local police or consumer-fraud line. Tell someone you trust."),
            trace=tr_.steps, lang=reply, message_lang=ing.lang)

    it = intent_stage.diagnose(ing)
    tr_.add("intent", "flag" if it.high_risk or it.pressure else "pass", it.summary())

    case = engine.investigate(ing, it, tr_, run)  # first pass, then loops until confident or out of budget
    ledger, d, out, f = case.ledger, case.decision, case.out, case.f
    tell = str(out.get("the_tell", ""))[:400] if out else ""
    action = str(out.get("action", ""))[:400] if out else ""
    abstract, phrase = (str(out.get("abstract_example", "")), str(out.get("tell_phrase", ""))) if out else ("", "")

    if d.verdict == Verdict.SAFE and case.votes:
        concern = analysis.critic(ing, it, f)
        if concern:
            d = gates.Decision(Verdict.UNSURE, "low", [T("second opinion: {concern}", concern=concern)])
            ledger.add("model", "critic", "scam", "weak", T("A second reviewer was worried: {concern}", concern=concern))
            tr_.add("critic", "flag", "{concern}", concern=concern)
        else:
            ledger.add("model", "critic", "safe", "weak", T("A second reviewer looked for risk signals and found none"))
            tr_.add("critic", "pass", "second reviewer found nothing")

    tactics = ledger.tactic_hits()
    verdict, first = d.verdict, (tactics[0].id if tactics else None)
    if not tell and first:
        tell = (f"“{tactics[0].quote}”{'：' if reply != 'en' else ': '}" if tactics[0].quote else "") + tactic_text(first, "tell", reply, TACTICS)
    if not action:
        action = tactic_text(first, "action", reply, TACTICS) if first and verdict != Verdict.SAFE else T(CAVEAT)
    if verdict == Verdict.SAFE and not tell:
        tell = T("Nothing here asks for money, codes, passwords or a rush, and I found no red flags.")
    tell, action, fixes = gates.output_gate(verdict, tell, action, T(CAVEAT), reply)
    tr_.add("output", "flag" if fixes else "pass", "; ".join(fixes) if fixes else "tone and safety rules satisfied")

    ok, why = gates.flywheel_gate(d, ledger, reply)
    added: list[str] = []
    if ok and store:
        ids = ledger.tactic_ids()
        phrase = phrase or tactics[0].quote
        # Prefer the model's name-free rewrite; otherwise the deterministic scrub (names can slip through offline).
        library.add_user_example(abstract or ing.text, ids, phrase, tell, action)
        model.record_exposure(ids)
        added = ids
    tr_.add("flywheel", "pass" if added else "skip", why)

    run.meta["evidence"] = [{"kind": e.kind, "source": e.source, "supports": e.supports, "strength": e.strength, "tactic": e.tactic} for e in ledger.items]
    return CheckResult(verdict=verdict, headline=T(HEADLINES[verdict]), tell=tell, action=action, tactics=tactics, added_to_training=added, evidence=ledger.items,
                       used_ai=bool(case.votes), confidence=d.confidence, trace=tr_.steps, lang=reply, message_lang=ing.lang)
