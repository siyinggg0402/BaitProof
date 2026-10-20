"""Stage 1, ingest gate: normalise, scan for injection / victim language, extract entities."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.domain import privacy
from core.storage import library

from .knowledge import AMBIGUOUS_BRANDS, BRANDS, INJECTION_RE, RAILS, VICTIM_RE

MAX_LEN = 4000
STOPWORDS = frozenset("the and you your to is a of for in on it i we are be this that with at my me can will please have has not from or if as so by an".split())


def looks_english(text: str) -> bool:
    words = re.findall(r"[^\W\d_]+", text.lower())
    letters = [c for c in text if c.isalpha()]
    if not words or not letters:
        return False
    foreign = sum(ord(c) > 0x24F for c in letters) / len(letters)  # non-Latin scripts
    return foreign < 0.1 and sum(w in STOPWORDS for w in words) / len(words) >= 0.15
AMOUNT_RE = re.compile(r"[$€£]\s?\d[\d,.]*|\b\d[\d,.]*\s?(?:dollars|usd|eur)\b", re.I)


@dataclass
class Entities:
    hosts: list[str] = field(default_factory=list)
    amounts: list[str] = field(default_factory=list)
    rails: dict[str, str] = field(default_factory=dict)  # rail -> matched text
    brands: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)  # digits only; checked locally, never sent to any service
    phone_raw: dict[str, str] = field(default_factory=dict)  # digits -> the text as written (for quoting)


@dataclass
class Ingested:
    text: str
    redacted: str  # what may be sent to a model: no emails / phone numbers / link paths
    entities: Entities
    injection: bool
    victim: bool
    english: bool  # the rule set only understands English, so rules alone can't clear anything else


def ingest(raw: str) -> Ingested:
    text = re.sub(r"[ \t]+", " ", raw.replace("\x00", "")).strip()[:MAX_LEN]
    if not text:
        raise ValueError("empty message")
    hosts = list(dict.fromkeys(library.host_of(m.group(0)) for m in library.URL_RE.finditer(text)))
    low = text.lower()
    ent = Entities(
        hosts=hosts,
        amounts=AMOUNT_RE.findall(text),
        rails={k: m.group(0) for k, p in RAILS.items() if (m := p.search(text))},
        brands=[b for b in BRANDS if b not in AMBIGUOUS_BRANDS and re.search(rf"\b{b}\b", low)],
        phones=privacy.phones_in(text),
        phone_raw=privacy.phone_matches(text),
    )
    return Ingested(text, library.redact(text), ent, bool(INJECTION_RE.search(text)), bool(VICTIM_RE.search(text)), looks_english(text))
