"""Stage 4, red-flag analysis. Rule-based tactics always run; the model (if configured) adds judgement.
Every tactic carries a QUOTE so the grounding gate can verify it."""
from __future__ import annotations

from core.ai import llm
from core.ai.prompts import CHECK_SYSTEM, CRITIC_SYSTEM
from core.domain.schemas import TacticHit, Verdict
from core.domain.tactics import TACTICS, valid

from .evidence import Ledger
from .ingest import Ingested
from .intent import Intent
from .knowledge import RULES
from .tools import Findings


STRONG_RULE_TACTICS = {"remote-access-request"}  # a pattern hit that is near-conclusive on its own


def rule_evidence(ing: Ingested, intent: Intent, f: Findings, ledger: Ledger) -> None:
    """Independent (non-model) evidence from phrase rules, the domain/rail tools and the intent diagnosis."""
    for tid, pats in RULES.items():
        for p in pats:
            if m := p.search(ing.text):
                q = m.group(0)[:80]
                ledger.add("rule", "pattern", "scam", "strong" if tid in STRONG_RULE_TACTICS else "medium",
                           f"“{q}” is a known scam phrase ({TACTICS[tid]['label'].lower()})", q, tid)
                break
    for host, why in f.hard_hosts.items():
        ledger.add("tool", "domain_check", "scam", "strong", f"The link {host} {'; '.join(why)}", host, "lookalike-link")
    for host, why in f.soft_hosts.items():
        ledger.add("tool", "domain_check", "scam", "weak", f"The link {host} {'; '.join(why)}", host, "lookalike-link")
    for r in f.irreversible_rails:
        ledger.add("tool", "payment_rail", "scam", "strong", f"Asks for payment by {r.replace('-', ' ')}, which can't be taken back",
                   ing.entities.rails[r], "irreversible-payment")
    if "share_code" in intent.asks and intent.evidence.get("share_code"):
        ledger.add("intent", "ask:share_code", "scam", "strong", "Asks you to hand over a code that is the key to your account",
                   intent.evidence["share_code"], "otp-credential-phish")
    if "pay" in intent.asks and intent.pressure:
        ledger.add("intent", "ask:pay+pressure", "scam", "strong", "Asks you to pay while rushing you",
                   intent.evidence.get("pressure", ""), None)
    if ing.injection:
        ledger.add("rule", "injection", "scam", "medium", "The message tries to give the checker instructions, which real messages never do")
    for note in f.web_notes:  # untrusted web text: shown, never weighed
        ledger.add("tool", "reputation", "neutral", "weak", "Web note (unverified): " + note[:200])


def safe_evidence(ing: Ingested, intent: Intent, ledger: Ledger) -> None:
    if not ledger.scam() and not intent.high_risk and "click" not in intent.asks and not intent.pressure and not ing.injection:
        ledger.add("intent", "benign-intent", "safe", "medium", "It asks for nothing risky: no money, codes, passwords, links or installs, and it doesn't rush you")


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
