from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Verdict(str, Enum):
    SCAM = "scam"
    LIKELY_SCAM = "likely_scam"
    SAFE = "safe"  # always shown as "looks safe, but verify"
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
    kind: str  # rule | intent | tool | reference | model
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


class LinkInfo(BaseModel):
    """What we found out about one link in the message, in the reply language, for the 'Links' panel."""
    host: str
    status: str  # official | known_phishing | lookalike | shortener | suspicious | unverified | established
    label: str = ""  # a short phrase, e.g. "Looks like DHL but isn't"
    notes: list[str] = Field(default_factory=list)  # plain-language facts ("registered 3 days ago")
    expanded_to: str = ""  # for a short link: the host it really goes to
    age_days: int | None = None


CHANNELS = ("sms", "whatsapp", "telegram", "wechat", "email", "social", "app", "website", "other")


class Origin(BaseModel):
    """Where a message came from, as far as we could tell: read off a screenshot (the app, the chat, the sender shown) or taken from a Telegram forward. It is
    UNVERIFIED context: shown to the person, given to the checker as a hint, and used only to know which company to look up. It never decides a verdict."""
    channel: str = ""  # one of CHANNELS, or ""
    app: str = ""  # the app, service or brand whose screen it is
    sender: str = ""  # the name or number shown as the sender
    forwarded_from: str = ""  # for a Telegram forward: the person or channel it was forwarded from

    def names(self) -> list[str]:
        """Names a company lookup may be asked about: the app/brand, a sender that is a name (not a number), and a forward's source."""
        out = []
        for v in (self.app, self.sender, self.forwarded_from):
            v = " ".join(v.split())
            if v and sum(c.isdigit() for c in v) <= len(v) // 3 and v.lower() not in (n.lower() for n in out):
                out.append(v)
        return out

    def empty(self) -> bool:
        return not (self.channel or self.app or self.sender or self.forwarded_from)


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
    links: list[LinkInfo] = Field(default_factory=list)
    source: str = "text"  # text | screenshot | voice: how the message reached us
    read_text: str = ""  # for a screenshot or voice note: what we read or heard (the user can see and correct it)
    origin: Origin | None = None  # where it seems to have come from (unverified)
    origin_note: str = ""  # that, as a sentence in the reply language ("A screen inside Tomoro Coffee"); empty when unknown


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
