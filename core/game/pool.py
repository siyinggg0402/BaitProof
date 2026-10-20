"""Everything the game can show: labelled messages with the correct answer and the explanation.
Sources: the curated seed bank, the authored reference bank, and the scams this person's own circle forwarded."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from core.ai import fewshot
from core.domain import i18n
from core.domain.lang import CJK
from core.domain.tactics import TACTICS
from core.storage import library

SAFE_TELL = "Nothing here asks for money, codes, passwords or a rush, so this one is fine."


@dataclass
class Item:
    id: str
    text: str
    truth: str  # scam | safe | unsure
    tactics: list[str] = field(default_factory=list)
    tell: str = ""
    tell_phrase: str = ""
    action: str = ""
    source: str = "seed"  # seed | bank | yours

    @property
    def tactic(self) -> str:
        return next((t for t in self.tactics if t in TACTICS), "")


def _id(text: str) -> str:
    return "g" + hashlib.sha1(" ".join(text.lower().split()).encode()).hexdigest()[:10]


def build_pool(lang: str = "en") -> list[Item]:
    """Newest-first priority: the person's own scams (any language: they are from their own circle), then the curated seeds for `lang`, then the
    authored bank (English only). Duplicates removed."""
    lang = i18n.norm(lang)
    safe_tell = i18n.tr(SAFE_TELL, lang)
    items: dict[str, Item] = {}

    def add(it: Item) -> None:
        items.setdefault(it.id, it)

    for e in library.user_examples():
        add(Item(_id(e["text"]), e["text"], "scam", list(e["tactics"]), e["tell"], e["tell_phrase"], e["action"], "yours"))
    for e in library.seed_examples(lang):
        if e["is_scam"]:
            add(Item(_id(e["text"]), e["text"], "scam", list(e["tactics"]), e["tell"], e["tell_phrase"], e["action"], "seed"))
        else:
            add(Item(_id(e["text"]), e["text"], "safe", [], e["tell"] or safe_tell, "", e["action"], "seed"))
    for b in (fewshot.load_authored() if lang == "en" else []):
        truth = "scam" if b.verdict in fewshot.SCAMMY else b.verdict
        why = b.why[:1].upper() + b.why[1:] + "." if b.why else ""
        add(Item(_id(b.text), b.text, truth, list(b.tactics), why if truth != "safe" else (why or SAFE_TELL), "", "", "bank"))
    return list(items.values())


def is_cjk(text: str) -> bool:
    return bool(CJK.search(text))


# A clause ends at full-width punctuation, or at ASCII punctuation followed by a space or the end (so "http://a.top" and "3.5" stay in one piece).
_CLAUSE = re.compile(r"(?:[^，。！？；：、,.!?;:\n]|[,.!?;:](?=\S))+[，。！？；：、]*(?:[,.!?;:](?=\s|$))*")


def words(text: str) -> list[str]:
    """The tappable units of a message. Chinese has no spaces, so its units are clauses; everything else is split on spaces."""
    if is_cjk(text):
        return [m.group(0) for m in _CLAUSE.finditer(text)]
    return text.split()


def norm_word(w: str) -> str:
    return re.sub(r"[^\w£$€%]", "", w.lower())


def phrase_span(text: str, phrase: str) -> tuple[int, int] | None:
    """Character range of the giveaway inside the message, for highlighting."""
    if not phrase:
        return None
    i = text.lower().find(phrase.lower())
    return (i, i + len(phrase)) if i >= 0 else None


def tell_score_clauses(item: Item, picked: list[int]) -> str:
    """Spot-the-tell for Chinese: the units are clauses. Correct when the chosen clauses cover most of the clauses the giveaway touches,
    without grabbing most of the message; partial when at least one is right (the same bar as the English word version)."""
    units = words(item.text)
    spans, pos = [], 0
    for u in units:
        i = item.text.index(u, pos)
        spans.append((i, i + len(u)))
        pos = i + len(u)
    ph = phrase_span(item.text, item.tell_phrase)
    sel = {i for i in picked if 0 <= i < len(units)}
    target = {k for k, (a, b) in enumerate(spans) if ph and a < ph[1] and ph[0] < b}
    if not target or not sel:
        return "wrong"
    hit = len(target & sel)
    recall, precision = hit / len(target), hit / len(sel)
    grabbed_most = len(sel) > 0.7 * len(units)
    return "correct" if recall >= 0.6 and precision >= 0.5 and not grabbed_most else ("partial" if hit else "wrong")
