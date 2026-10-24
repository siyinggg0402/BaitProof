"""Check pipeline (PLAN §6a): ingest -> victim triage -> intent -> tools -> analysis -> grounding -> arbiter
-> critic -> compose -> flywheel gate. Each gate writes to the trace."""
from __future__ import annotations

import os

from core import obs
from core.ai import llm
from core.lang import i18n
from core.lang.i18n import tactic_text, tr
from core.lang.text import detect
from core.domain import intents
from core.domain.schemas import CheckResult, Origin, Verdict
from core.domain.tactics import TACTICS
from core.obs.logger import fingerprint
from core.obs.metrics import cost_usd
from core.storage import library, model

from . import analysis, engine, gates, intent as intent_stage, linkinfo, localize
from .ingest import ingest
from .origin import describe as describe_origin
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
    return d if d in ("zh", "zh-Hant", "ms", "ta") else "en"


def check_message(text: str, store: bool = True, on_event=None, log: bool = True, lang: str | None = None, *, source: str = "text", read_text: str = "", origin: Origin | None = None) -> CheckResult:
    """Run one check. Never crashes on internal errors (returns a cautious 'not sure'), always logs one structured event.
    `lang` is the language to answer in (en | zh | zh-Hant); by default the message's own.
    `source` says how the message reached us (text | screenshot | voice) and `read_text` is what we read or heard, handed back on the result so the
    user can see and correct it; neither changes the verdict, and the log keeps `source` only (never the text).
    `origin` is where the message seems to have come from (read off a screenshot, or a Telegram forward): unverified context that is shown back, given to the
    checker as a hint and used to know which company to look up; the log keeps only its channel."""
    run = obs.start()
    run.meta["source"] = source
    if origin is not None and origin.channel:
        run.meta["origin_channel"] = origin.channel
    reply = reply_language(text, lang)
    trace = Trace(on_event, reply)
    try:
        result = _check(text, store, trace, run, reply, origin)
    except ValueError:
        raise  # invalid input (empty message): the caller reports it
    except Exception as e:
        obs.emit({"kind": "error", "where": "check", "type": type(e).__name__, "id": run.id})
        trace.add("guard", "block", "internal error: returning a cautious answer")
        result = CheckResult(verdict=Verdict.UNSURE, headline=tr(HEADLINES[Verdict.UNSURE], reply), confidence="low", lang=reply,
                             tell=tr("I couldn't finish checking this message.", reply),
                             action=tr("I can't be sure. If it asks for money, codes or a rush, check first using an official number or website you already trust.", reply), trace=trace.steps)
    result.check_id = run.id
    result.source, result.read_text = source, read_text
    if origin is not None and not origin.empty():
        result.origin, result.origin_note = origin, describe_origin(origin, result.lang)
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


def _check(text: str, store: bool, tr_: Trace, run: obs.Run, reply: str = "en", origin: Origin | None = None) -> CheckResult:
    ing = ingest(text)
    ing.reply = reply
    ing.origin = origin
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

    plain_code = it.purpose == "one-time-code" and intents.clearing_conditions_met("one-time-code", ing.text, it.asks)  # the rules recognised a plain login-code delivery that asks for nothing: a second reviewer only ever misreads its "do not share this code" as secrecy
    if d.verdict == Verdict.SAFE and case.votes and not plain_code:
        concern = analysis.critic(ing, it, f)
        if concern and not localize.in_script(concern, reply):
            concern = (localize.translate([concern], reply) or [T("a second reviewer was worried")])[0]
        if concern:
            d = gates.Decision(Verdict.UNSURE, "low", [T("second opinion: {concern}", concern=concern)])
            ledger.add("model", "critic", "scam", "weak", T("A second reviewer was worried: {concern}", concern=concern))
            tr_.add("critic", "flag", "{concern}", concern=concern)
        else:
            ledger.add("model", "critic", "safe", "weak", T("A second reviewer looked for risk signals and found none"))
            tr_.add("critic", "pass", "second reviewer found nothing")

    tell, action = localize.explain_in(reply, tell, action, ledger)  # the model's sentences, in the reader's language (or "" to use the static text below)
    tactics = ledger.tactic_hits()
    verdict, first = d.verdict, (tactics[0].id if tactics else None)
    if not tell and first:
        tell = (f"“{tactics[0].quote}”{': ' if reply in ('en', 'ms', 'ta') else '：'}" if tactics[0].quote else "") + tactic_text(first, "tell", reply, TACTICS)
    if not action or (reply == "ta" and first and verdict != Verdict.SAFE):
        # what to do is the part that must be right: in Tamil it is always our own written line for the trick (the model's Tamil has not been checked by a Tamil speaker)
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

    try:
        links = linkinfo.build(ing, f, reply)
    except Exception:  # the panel is a convenience: never let it break a check
        links = []
    run.meta["links"] = len(links)
    run.meta["short_links_followed"] = sum(1 for d in f.shorts.values() if d)
    run.meta["evidence"] = [{"kind": e.kind, "source": e.source, "supports": e.supports, "strength": e.strength, "tactic": e.tactic} for e in ledger.items]
    return CheckResult(verdict=verdict, headline=T(HEADLINES[verdict]), tell=tell, action=action, tactics=tactics, added_to_training=added, evidence=ledger.items,
                       used_ai=bool(case.votes), confidence=d.confidence, trace=tr_.steps, lang=reply, message_lang=ing.lang, links=links)
