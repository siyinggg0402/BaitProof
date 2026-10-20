"""The investigation engine: a first pass (rules, free local tools, model), then a bounded loop that keeps gathering evidence
until the arbiter is confident or a budget runs out. It never loops forever and never forces a verdict:
if it cannot become confident it stops and says so (the answer stays 'not sure')."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field

from core.ai import llm
from core.domain.schemas import Verdict
from core.domain.tactics import TACTICS

from . import analysis, gates, planner, preconditions, tools
from .evidence import Ledger
from .ingest import Ingested
from .intent import Intent
from .trace import Trace

MAX_ROUNDS = int(os.getenv("BAITPROOF_MAX_ROUNDS", "3"))  # total rounds including the first pass
MAX_LLM_CALLS = int(os.getenv("BAITPROOF_MAX_LLM_CALLS", "10"))  # per check
MAX_SECONDS = float(os.getenv("BAITPROOF_MAX_SECONDS", "25"))  # wall clock, checked before each extra round


def _direction(v: Verdict) -> str:
    return "scam" if v in (Verdict.SCAM, Verdict.LIKELY_SCAM) else ("safe" if v == Verdict.SAFE else "unsure")


@dataclass
class Case:
    ing: Ingested
    it: Intent
    f: tools.Findings
    gate: tools.ToolGate
    ledger: Ledger
    tr: Trace
    run: object
    votes: list[Verdict] = field(default_factory=list)  # model opinions on the CURRENT evidence snapshot
    out: dict | None = None  # latest primary model output (the tell/action/abstract come from it)
    decision: gates.Decision | None = None
    rounds: int = 1
    second_looked: bool = False
    t0: float = field(default_factory=time.perf_counter)

    def model_verdict(self) -> Verdict | None:
        """The model's combined opinion. 'unsure' is neutral: only a direct scam-vs-safe contradiction makes it unsure."""
        if not self.votes:
            return None
        dirs = [_direction(v) for v in self.votes]
        if "scam" in dirs and "safe" in dirs:
            return Verdict.UNSURE  # the model contradicts itself
        if "scam" in dirs:
            return next(v for v in reversed(self.votes) if _direction(v) == "scam")
        if "safe" in dirs and dirs.count("safe") >= dirs.count("unsure"):
            return Verdict.SAFE
        return Verdict.UNSURE

    def scam_votes(self) -> int:
        return sum(1 for v in self.votes if _direction(v) == "scam")

    def decide(self) -> gates.Decision:
        self.decision = gates.arbitrate(self.ledger, self.it, self.f, self.model_verdict(), self.ing.injection, self.ing.english, self.scam_votes())
        return self.decision

    def model_pass(self, second: bool = False) -> bool:
        """Ask the model, admit only claims that quote the message, and record its vote. False if there is no model/answer."""
        out = analysis.model_analysis(self.ing, self.it, self.f, second_look=second)
        if not out:
            return False
        verdict, proposed = analysis.parse_model(out)
        kept, unquoted = gates.grounding_gate(proposed, self.ing.text, self.ing.redacted)
        kept, impossible = preconditions.filter_claims(kept, self.ing, self.it, self.f)  # a claim must also be possible for THIS message
        dropped = [f"{t}: quote not found in the message" for t in unquoted] + impossible
        for t in kept:
            self.ledger.add("model", "analysis", "scam", "medium", t.why or f"The AI reviewer spotted: {TACTICS[t.id]['label'].lower()}", t.quote, t.id)
        if verdict == Verdict.SAFE:
            self.ledger.add("model", "second-look" if second else "analysis", "safe", "medium",
                            "A second look by the AI reviewer also found nothing suspicious" if second else "The AI reviewer found nothing suspicious")
        self.votes.append(verdict)
        if not second:
            self.out = out
        label = "second look" if second else "analysis"
        self.tr.add("analysis" if not second else "second-look", "pass", f"model {label}: {verdict.value}; {len(proposed)} tactic(s) proposed")
        self.tr.add("grounding", "flag" if dropped else "pass",
                    f"dropped {len(dropped)} AI claim(s) ({'; '.join(dropped)})" if dropped else f"{len(kept)} AI claim(s) verified against the message")
        return True

    def stop_reason(self) -> str:
        d = self.decision
        if d.confidence == "high":
            return "confident enough"
        if self.rounds >= MAX_ROUNDS:
            return f"reached the round limit ({MAX_ROUNDS})"
        if time.perf_counter() - self.t0 > MAX_SECONDS:
            return "time budget used up"
        if len(self.run.llm) >= MAX_LLM_CALLS:
            return "model-call budget used up"
        return ""


def investigate(ing: Ingested, it: Intent, tr: Trace, run) -> Case:
    f, gate = tools.run_tools(ing, tr, it.claimed if it.claimed_kind in ("organisation", "authority") else "")
    case = Case(ing, it, f, gate, Ledger(), tr, run)
    analysis.rule_evidence(ing, it, f, case.ledger)
    if not case.model_pass():
        tr.add("analysis", "skip", "no AI configured: using built-in rules only")
        tr.add("grounding", "pass", f"{len(case.ledger.tactic_ids())} red flag(s) from built-in rules")
    analysis.safe_evidence(ing, it, case.ledger, f)
    d = case.decide()
    tr.add("arbiter", "pass", f"{d.verdict.value} ({d.confidence} confidence): " + "; ".join(d.reasons))
    _loop(case)
    return case


def _loop(case: Case) -> None:
    ing, it, f, gate, ledger, tr = case.ing, case.it, case.f, case.gate, case.ledger, case.tr
    while True:
        why = case.stop_reason()
        if why:
            break
        qs = planner.open_questions(ing, it, f, gate)
        before = len(ledger.items)
        if any(q.calls for q in qs):
            calls, who = planner.llm_plan(ing, qs, ledger, gate, f)
            ran = gate.run(calls, f)
            action = f"asked {', '.join(f'{t}({a[:24]})' for t, a in calls) or 'nothing'} ({who} chose)"
            analysis.rule_evidence(ing, it, f, ledger)
            if ran and llm.available():  # re-read the message knowing what we just learned
                ledger.clear_model()
                case.votes, case.second_looked = [], False
                case.model_pass()
        elif llm.available() and not case.second_looked and case.decision.model_dependent:  # only when the model's opinion is what's in doubt
            case.second_looked = True
            if not case.model_pass(second=True):
                why = "second look unavailable"
                break
            action = "took a second look with a different framing"
        else:
            why = "nothing more to check" if not qs else "nothing more any tool can answer"
            break
        analysis.safe_evidence(ing, it, ledger, f)
        d = case.decide()
        case.rounds += 1
        case.run.rounds = case.rounds
        tr.add("loop", "pass", f"round {case.rounds}: {action} → {len(ledger.items) - before:+d} fact(s); now {d.verdict.value} ({d.confidence} confidence)")
    tr.add("sufficiency", "pass" if case.decision.confidence == "high" else "flag", why)
