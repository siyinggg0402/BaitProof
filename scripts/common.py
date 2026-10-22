"""Pieces every evaluation script needs: the plain-model baseline, normalised verdicts, counting, one results table, and a switch that keeps a
run offline so it never spends model credit."""
from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass

import core  # noqa: F401  (loads .env)
from core.ai import llm
from core.domain.privacy import redact
from core.obs.metrics import cost_usd

# The naive baseline everything is compared with: one model call, no intent, tools, evidence or gates.
BASELINE_SYSTEM = """You are a scam detector. Decide whether the message is a scam. Return ONLY JSON: {"verdict": "scam" | "safe" | "unsure"}."""


def plain_verdict(text: str) -> str:
    """scam | safe | unsure | error, from ONE plain model call."""
    try:
        v = llm.chat_json(BASELINE_SYSTEM, "MESSAGE:\n" + redact(text), heavy=True, purpose="baseline").get("verdict", "unsure")
    except llm.LLMUnavailable:
        return "error"
    return v if v in ("scam", "safe", "unsure") else "unsure"


def pipeline_verdict(text: str) -> str:
    """scam | safe | unsure | error, from the whole pipeline ('likely scam' counts as scam; victim support is not a verdict on the message)."""
    from core.pipelines.check import check_message

    try:
        v = check_message(text, store=False, log=False).verdict.value
    except Exception:
        return "error"
    return "scam" if v == "likely_scam" else ("unsure" if v == "victim_support" else v)


@contextmanager
def offline(net: bool = False):
    """Rules only: blank the model key (dotenv does not override a variable that is already set), and optionally the network tools too. The downloaded
    phishing list is switched off as well, so a number never depends on which day the list was fetched."""
    keep = {k: os.environ.get(k) for k in ("NEBIUS_API_KEY", "BAITPROOF_NET_TOOLS", "BAITPROOF_BLOCKLIST")}
    os.environ["NEBIUS_API_KEY"] = ""
    os.environ["BAITPROOF_BLOCKLIST"] = "0"
    if net:
        os.environ["BAITPROOF_NET_TOOLS"] = "0"
    try:
        yield
    finally:
        for k, v in keep.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@dataclass
class Tally:
    scams: int = 0
    caught: int = 0  # scams called scam (or likely scam)
    scam_unsure: int = 0
    false_safe: int = 0  # scams called safe: the number that must stay 0
    genuine: int = 0
    cleared: int = 0  # genuine messages called safe
    genuine_unsure: int = 0
    false_alarm: int = 0  # genuine messages called scam
    errors: int = 0


def tally(pairs) -> Tally:
    """pairs: (is_scam, verdict) with verdict in scam | safe | unsure | error."""
    t = Tally()
    for is_scam, v in pairs:
        t.errors += v == "error"
        if is_scam:
            t.scams += 1
            t.caught += v == "scam"
            t.scam_unsure += v == "unsure"
            t.false_safe += v == "safe"
        else:
            t.genuine += 1
            t.cleared += v == "safe"
            t.genuine_unsure += v == "unsure"
            t.false_alarm += v == "scam"
    return t


def header(first: str = "system", width: int = 8) -> str:
    return (f"{first:{width}} {'caught':>9} {'unsure':>7} {'FALSE-SAFE':>11} | {'cleared':>9} {'unsure':>7} {'FALSE-ALARM':>12} | {'secs':>6}")


def row(label: str, t: Tally, secs: float = 0.0, cost: float | None = None, width: int = 8) -> str:
    out = (f"{label:{width}} {t.caught:>4}/{t.scams:<4} {t.scam_unsure:>7} {t.false_safe:>11} | {t.cleared:>4}/{t.genuine:<4} {t.genuine_unsure:>7} {t.false_alarm:>12} | {secs:>6.0f}")
    return out + (f"  ({t.errors} errors)" if t.errors else "") + (f"  ≈${cost:.4f}" if cost is not None else "")


class Spend:
    """Tokens and cost of the model calls made since it was created."""

    def __init__(self) -> None:
        self._before = dict(llm.USAGE)

    @property
    def tokens(self) -> tuple[int, int]:
        return llm.USAGE["prompt_tokens"] - self._before["prompt_tokens"], llm.USAGE["completion_tokens"] - self._before["completion_tokens"]

    @property
    def usd(self) -> float:
        return cost_usd(*self.tokens)
