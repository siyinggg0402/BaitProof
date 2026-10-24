"""Stage 1, ingest gate: normalise, scan for injection / victim language, extract entities."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from core.lang import text as L
from core.domain import privacy
from core.domain.schemas import Origin
from core.lang import ms as MS
from core.lang import ta as TA
from core.lang import zh as ZH
from core.domain.intents import WARNING_FOREIGN
from core.lang.text import Dual
from core.storage import library

from . import links as LK
from .knowledge import AMBIGUOUS_BRANDS, BRANDS, INJECTION_RE, RAILS, VICTIM_RE, ZH_BRAND_NAMES

MAX_LEN = 4000
AMOUNT_RE = Dual(r"[$€£₹]\s?\d[\d,.]*|\bRs\.? ?\d[\d,.]*|\bINR\.? ?\d[\d,.]*|\b\d[\d,.]*\s?(?:dollars|usd|eur|rupees)\b|\bRM\s?\d[\d,.]*|\bS\$\s?\d[\d,.]*", ZH.AMOUNT, MS.AMOUNT, TA.AMOUNT)


@dataclass
class Entities:
    hosts: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)  # every link as it was written (with its path), for tools that need more than the host (a short link)
    amounts: list[str] = field(default_factory=list)
    rails: dict[str, str] = field(default_factory=dict)  # rail -> matched text
    brands: list[str] = field(default_factory=list)
    phones: list[str] = field(default_factory=list)  # digits only; checked locally, never sent to any service
    phone_raw: dict[str, str] = field(default_factory=dict)  # digits -> the text as written (for quoting)
    brand_quotes: dict[str, str] = field(default_factory=dict)  # Chinese brand key -> the name as written (for quoting)
    emails: list[str] = field(default_factory=list)  # addresses as written: an email's domain is NOT a link to that website


@dataclass
class Ingested:
    text: str
    redacted: str  # what may be sent to a model: no emails / phone numbers / link paths
    entities: Entities
    injection: bool
    victim: bool
    english: bool  # True when our rules understand the language (English or Chinese); otherwise rules alone can't clear anything
    lang: str = "en"  # en | zh | zh-Hant | ms | ja | ko | ... | other (see core.lang.text)
    reply: str = "en"  # the language the ANSWER is written in (en | zh | zh-Hant): the user's choice, set by the pipeline
    origin: Origin | None = None  # where the message seems to have come from (unverified context), set by the pipeline


def ingest(raw: str) -> Ingested:
    text = re.sub(r"[ \t]+", " ", raw.replace("\x00", "")).strip()[:MAX_LEN]
    if not text:
        raise ValueError("empty message")
    email_spans = [m.span() for m in library.EMAIL_RE.finditer(text)]
    hosts, urls = [], []
    cleaned = LK.deobfuscate(text)  # a link written to dodge a filter (hxxp://, [.], full-width dots) is read from a cleaned COPY; `text` stays as the user wrote it
    for scan in ([text] if cleaned == text else [text, cleaned]):
        for h, u in LK.find(scan, [m.span() for m in library.EMAIL_RE.finditer(scan)]):  # "claims@yahoo.com" is an address, not a link to yahoo.com
            if h not in hosts:
                hosts.append(h)
            if u not in urls:
                urls.append(u)
    low = text.lower()
    simp = L.to_simplified(text) if L.CJK.search(text) else ""  # Chinese brand names are matched in Simplified so Traditional text counts too
    lang = L.detect(text)
    L.CURRENT.set(lang)  # the Malay/Indonesian twin patterns key off this
    ent = Entities(
        hosts=hosts,
        urls=urls,
        emails=[library.EMAIL_RE.search(text[a:b]).group(0).lower() for a, b in email_spans],
        amounts=AMOUNT_RE.findall(text),
        rails={k: m.group(0) for k, p in RAILS.items() if (m := p.search(WARNING_FOREIGN.sub(" ", text)))},
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
