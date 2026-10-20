"""Eval harness for Check: the headline number is the FALSE-SAFE rate, which must stay 0."""
from __future__ import annotations

from core.domain.schemas import Verdict
from core.storage import library

from .pipeline import check_message


def run() -> dict:
    scams = [e for e in library.seed_examples() if e["is_scam"]]
    legit = [e for e in library.seed_examples() if not e["is_scam"]]
    r_scam = [check_message(e["text"], store=False, log=False).verdict for e in scams]
    r_legit = [check_message(e["text"], store=False, log=False).verdict for e in legit]
    flagged = (Verdict.SCAM, Verdict.LIKELY_SCAM)
    return {
        "scams": len(scams), "false_safe": sum(v == Verdict.SAFE for v in r_scam),
        "scam_caught_confident": sum(v in flagged for v in r_scam),
        "legit": len(legit), "false_alarm": sum(v in flagged for v in r_legit),
        "legit_cleared": sum(v == Verdict.SAFE for v in r_legit),
        "missed_ids": [e["id"] for e, v in zip(scams, r_scam) if v == Verdict.SAFE],
    }
