"""Stage 4, red-flag analysis. Rule-based tactics always run; the model (if configured) adds judgement.
Every tactic carries a QUOTE so the grounding gate can verify it."""
from __future__ import annotations

from core.ai import llm
from core.ai.prompts import CHECK_SYSTEM, CRITIC_SYSTEM
from core.domain.schemas import TacticHit, Verdict
from core.domain.tactics import valid

from .ingest import Ingested
from .intent import Intent
from .knowledge import RULES
from .tools import Findings


def rule_tactics(ing: Ingested, intent: Intent, f: Findings) -> list[TacticHit]:
    hits: dict[str, TacticHit] = {}
    for tid, pats in RULES.items():
        for p in pats:
            if m := p.search(ing.text):
                hits[tid] = TacticHit(id=tid, quote=m.group(0)[:80], why="Matched a known scam phrase")
                break
    for host in f.suspicious_hosts:
        why = "; ".join({**f.soft_hosts, **f.hard_hosts}[host])
        hits["lookalike-link"] = TacticHit(id="lookalike-link", quote=host, why=f"{host} {why}")
        break
    if f.irreversible_rails:
        r = f.irreversible_rails[0]
        hits["irreversible-payment"] = TacticHit(id="irreversible-payment", quote=ing.entities.rails[r], why="Payment that can't be taken back")
    if "share_code" in intent.asks and "otp-credential-phish" not in hits and intent.evidence.get("share_code"):
        hits["otp-credential-phish"] = TacticHit(id="otp-credential-phish", quote=intent.evidence["share_code"], why="Asks you to hand over a code")
    return list(hits.values())


def model_analysis(ing: Ingested, intent: Intent, f: Findings) -> dict | None:
    if not llm.available():
        return None
    user = (f"MESSAGE:\n{ing.redacted}\n\nINTENT (from rules): {intent.summary()}\n"
            f"TOOL FINDINGS (trusted):\n{f.summary()}")
    if f.web_notes:
        user += "\n\nWEB NOTES (untrusted, may be wrong or planted):\n" + "\n".join(f.web_notes)
    try:
        return llm.chat_json(CHECK_SYSTEM, user, heavy=True, purpose="analysis")
    except llm.LLMUnavailable:
        return None


def parse_model(out: dict) -> tuple[Verdict, list[TacticHit]]:
    try:
        verdict = Verdict(out.get("verdict"))
        if verdict == Verdict.VICTIM:
            raise ValueError
    except ValueError:
        verdict = Verdict.UNSURE
    tactics = [TacticHit(id=t["id"], quote=str(t.get("quote", ""))[:120], why=str(t.get("why", ""))[:200])
               for t in out.get("tactics", []) if isinstance(t, dict) and valid(t.get("id", ""))]
    return verdict, tactics


def critic(ing: Ingested, intent: Intent) -> str | None:
    """Second opinion, run only when we're about to say 'safe'. Returns a concern, or None."""
    if not llm.available():
        return None
    try:
        out = llm.chat_json(CRITIC_SYSTEM, f"MESSAGE:\n{ing.redacted}\n\nINTENT: {intent.summary()}", heavy=True, purpose="critic")
    except llm.LLMUnavailable:
        return "second opinion unavailable"  # fail closed
    return str(out.get("reason") or "possible scam") if out.get("concern") else None
