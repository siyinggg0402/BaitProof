from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    SCAM = "scam"
    LIKELY_SCAM = "likely_scam"
    SAFE = "safe"  # always shown as "looks safe, but verify" (PLAN §3)
    UNSURE = "unsure"
    VICTIM = "victim_support"


class Level(str, Enum):
    UNTESTED = "untested"
    WEAK = "weak"
    LEARNING = "learning"
    STRONG = "strong"


class TacticHit(BaseModel):
    id: str
    why: str = ""
    quote: str = ""  # exact words from the message; verified by the grounding gate


class Evidence(BaseModel):
    """One structured fact behind a verdict. `kind` says who produced it; model-only evidence is weighed less."""
    id: str = ""
    kind: str  # rule | intent | tool | model
    source: str  # e.g. pattern, domain_check, payment_rail, reputation, analysis, critic
    supports: str  # scam | safe | neutral
    strength: str  # weak | medium | strong
    claim: str  # plain-language statement shown to the user
    quote: str = ""  # exact words from the message, when the evidence is about the text
    tactic: str | None = None


class TraceStep(BaseModel):
    stage: str
    status: str  # pass | flag | skip | block
    detail: str
    ms: int = 0  # time since the previous step


class CheckResult(BaseModel):
    verdict: Verdict
    headline: str
    tell: str = ""
    action: str = ""
    tactics: list[TacticHit] = Field(default_factory=list)
    added_to_training: list[str] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    used_ai: bool = False
    confidence: str = "medium"
    trace: list[TraceStep] = Field(default_factory=list)
    check_id: str = ""
    lang: str = "en"  # the language the answer is written in (en | zh | zh-Hant), chosen by the user
    message_lang: str = "en"  # the language the checked message is in


class Drill(BaseModel):
    id: str
    tactic: str
    format: str  # spot-trick | highlight-tell | what-to-do | safe-reply
    scenario: str
    question: str
    options: list[str] = Field(default_factory=list)
    correct_index: int | None = None  # None => free text
    explanation: str = ""
    tell_phrase: str = ""
    reason: str = ""

    def public(self) -> dict:
        """What the browser sees: no answer."""
        return self.model_dump(exclude={"correct_index", "explanation", "tell_phrase"})


class Grade(BaseModel):
    result: str  # correct | partial | incorrect
    note: str
