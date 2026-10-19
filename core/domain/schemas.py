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


class TraceStep(BaseModel):
    stage: str
    status: str  # pass | flag | skip | block
    detail: str


class CheckResult(BaseModel):
    verdict: Verdict
    headline: str
    tell: str = ""
    action: str = ""
    tactics: list[TacticHit] = Field(default_factory=list)
    added_to_training: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    used_ai: bool = False
    confidence: str = "medium"
    trace: list[TraceStep] = Field(default_factory=list)


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
