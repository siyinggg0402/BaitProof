"""Evidence ledger: every stage adds structured facts; the verdict is computed from them and cites them.
Rules of the road: tool/rule/intent evidence is INDEPENDENT; model evidence is admitted only if grounded in the message
and counts for less. Web text (Tavily) is recorded as neutral: it is shown but can never move a verdict."""
from __future__ import annotations

from core.domain.schemas import Evidence, TacticHit

POINTS = {"weak": 1.0, "medium": 2.0, "strong": 3.0}
MODEL_DISCOUNT = 0.5


class Ledger:
    def __init__(self) -> None:
        self.items: list[Evidence] = []
        self._seen: set[tuple] = set()

    def add(self, kind: str, source: str, supports: str, strength: str, claim: str, quote: str = "", tactic: str | None = None) -> Evidence | None:
        key = (kind, source, supports, tactic, quote.strip().lower(), claim if not quote else "")
        if key in self._seen:
            return None
        self._seen.add(key)
        ev = Evidence(id=f"e{len(self.items) + 1}", kind=kind, source=source, supports=supports, strength=strength,
                      claim=claim[:240], quote=quote[:120], tactic=tactic)
        self.items.append(ev)
        return ev

    # -- views ---------------------------------------------------------------------------------------------------
    def scam(self) -> list[Evidence]:
        return [e for e in self.items if e.supports == "scam"]

    def safe(self) -> list[Evidence]:
        return [e for e in self.items if e.supports == "safe"]

    def independent_scam(self) -> list[Evidence]:
        return [e for e in self.scam() if e.kind != "model"]

    def strong_independent_scam(self) -> list[Evidence]:
        return [e for e in self.independent_scam() if e.strength == "strong"]

    def has_script_match(self) -> bool:
        return any(e.source.startswith("scenario:") and e.kind != "model" for e in self.scam())

    def tactic_ids(self) -> list[str]:
        return list(dict.fromkeys(e.tactic for e in self.scam() if e.tactic))

    def tactic_hits(self) -> list[TacticHit]:
        """One hit per tactic, backed by its strongest, preferably independent, evidence."""
        order = {"strong": 0, "medium": 1, "weak": 2}
        out = []
        for tid in self.tactic_ids():
            best = min((e for e in self.scam() if e.tactic == tid), key=lambda e: (e.kind == "model", order[e.strength]))
            out.append(TacticHit(id=tid, why=best.claim, quote=best.quote))
        return out

    def weight(self, supports: str) -> float:
        return sum(POINTS[e.strength] * (MODEL_DISCOUNT if e.kind == "model" else 1.0) for e in self.items if e.supports == supports)

    def has_independent_support(self) -> bool:
        """Flywheel requirement: at least one non-model scam fact of medium+ strength."""
        return any(e.strength in ("medium", "strong") for e in self.independent_scam())
