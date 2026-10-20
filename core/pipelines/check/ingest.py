"""Stage 1, ingest gate: normalise, scan for injection / victim language, extract entities."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.domain import lang as L
from core.domain import privacy
from core.domain import ms as MS
from core.domain import zh as ZH
from core.domain.lang import Dual
from core.storage import library

from .knowledge import AMBIGUOUS_BRANDS, BRANDS, INJECTION_RE, RAILS, VICTIM_RE, ZH_BRAND_NAMES

MAX_LEN = 4000
STOPWORDS = frozenset("the and you your to is a of for in on it i we are be this that with at my me can will please have has not from or if as so by an".split())


def looks_english(text: str) -> bool:
    words = re.findall(r"[^\W\d_]+", text.lower())
    letters = [c for c in text if c.isalpha()]
    if not words or not letters:
        return False
    foreign = sum(ord(c) > 0x24F for c in letters) / len(letters)  # non-Latin scripts
    return foreign < 0.1 and sum(w in STOPWORDS for w in words) / len(words) >= 0.15
AMOUNT_RE = Dual(r"[$€£]\s?\d[\d,.]*|\b\d[\d,.]*\s?(?:dollars|usd|eur)\b|\bRM\s?\d[\d,.]*|\bS\$\s?\d[\d,.]*", ZH.AMOUNT, MS.AMOUNT)


@dataclass
class Entities:
    hosts: list[str] = field(default_factory=list)
    amounts: list[str] = field(default_factory=list)
    rails: dict[str, str] = field(default_factory=dict)  # rail -> matched text
    brands: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)  # digits only; checked locally, never sent to any service
    phone_raw: dict[str, str] = field(default_factory=dict)  # digits -> the text as written (for quoting)
    brand_quotes: dict[str, str] = field(default_factory=dict)  # Chinese brand key -> the name as written (for quoting)


@dataclass
class Ingested:
    text: str
    redacted: str  # what may be sent to a model: no emails / phone numbers / link paths
    entities: Entities
    injection: bool
    victim: bool
    english: bool  # True when our rules understand the language (English or Chinese); otherwise rules alone can't clear anything
    lang: str = "en"  # en | zh | zh-Hant | ms | ja | ko | ... | other (see core.domain.lang)
    reply: str = "en"  # the language the ANSWER is written in (en | zh | zh-Hant): the user's choice, set by the pipeline


def ingest(raw: str) -> Ingested:
    text = re.sub(r"[ \t]+", " ", raw.replace("\x00", "")).strip()[:MAX_LEN]
    if not text:
        raise ValueError("empty message")
    hosts = list(dict.fromkeys(library.host_of(m.group(0)) for m in library.URL_RE.finditer(text)))
    low = text.lower()
    simp = L.to_simplified(text) if L.CJK.search(text) else ""  # Chinese brand names are matched in Simplified so Traditional text counts too
    lang = L.detect(text)
    L.CURRENT.set(lang)  # the Malay/Indonesian twin patterns key off this
    ent = Entities(
        hosts=hosts,
        amounts=AMOUNT_RE.findall(text),
        rails={k: m.group(0) for k, p in RAILS.items() if (m := p.search(text))},
        brands=list(dict.fromkeys([b for b in BRANDS if b not in AMBIGUOUS_BRANDS and re.search(rf"\b{b}\b", low)]
                                  + [key for name, key in ZH_BRAND_NAMES.items() if name in simp])),
        phones=privacy.phones_in(text),
        phone_raw=privacy.phone_matches(text),
    )
    for name, key in ZH_BRAND_NAMES.items():
        if key in ent.brands and key not in ent.brand_quotes and name in simp:
            q = L.Z(re.escape(name)).search(text)
            if q:
                ent.brand_quotes[key] = q.group(0)
    return Ingested(text, library.redact(text), ent, bool(INJECTION_RE.search(text)), bool(VICTIM_RE.search(text)), lang in L.RULES_LANGS, lang)
