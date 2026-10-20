"""Everything the game can show: labelled messages with the correct answer and the explanation.
Sources: the curated seed bank, the authored reference bank, and the scams this person's own circle forwarded."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from core.ai import fewshot
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


def build_pool() -> list[Item]:
    """Newest-first priority: the person's own scams, then the curated seeds, then the authored bank. Duplicates removed."""
    items: dict[str, Item] = {}

    def add(it: Item) -> None:
        items.setdefault(it.id, it)

    for e in library.user_examples():
        add(Item(_id(e["text"]), e["text"], "scam", list(e["tactics"]), e["tell"], e["tell_phrase"], e["action"], "yours"))
    for e in library.seed_examples():
        if e["is_scam"]:
            add(Item(_id(e["text"]), e["text"], "scam", list(e["tactics"]), e["tell"], e["tell_phrase"], e["action"], "seed"))
        else:
            add(Item(_id(e["text"]), e["text"], "safe", [], e["tell"] or SAFE_TELL, "", e["action"], "seed"))
    for b in fewshot.load_authored():
        truth = "scam" if b.verdict in fewshot.SCAMMY else b.verdict
        why = b.why[:1].upper() + b.why[1:] + "." if b.why else ""
        add(Item(_id(b.text), b.text, truth, list(b.tactics), why if truth != "safe" else (why or SAFE_TELL), "", "", "bank"))
    return list(items.values())


def words(text: str) -> list[str]:
    return text.split()


def norm_word(w: str) -> str:
    return re.sub(r"[^\w£$€%]", "", w.lower())


def phrase_span(text: str, phrase: str) -> tuple[int, int] | None:
    """Character range of the giveaway inside the message, for highlighting."""
    if not phrase:
        return None
    i = text.lower().find(phrase.lower())
    return (i, i + len(phrase)) if i >= 0 else None
