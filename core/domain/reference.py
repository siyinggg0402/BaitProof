"""A short, dated list of scam scripts that official bodies have named (data/reference/entries.json), matched EXACTLY against a message: no embeddings, no model.
This is the "retrieval" part of the checker: facts the model cannot know and that change (a new wave, a new rule), kept as data so a line can be added without code.
An entry applies only when its signature is in the message AND the message asks the reader to do something (or, for the bank-link entry, carries a link we could not
verify), and never when the sentence is itself a warning ("never share ..."): an advisory quotes the scam it warns about. A match is evidence like any other rule: it
names its source in the claim, counts as independent (not the model's opinion) and can only add to a verdict. The claims are English keys that i18n translates."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from core.lang.text import Z

PATH = Path(__file__).resolve().parents[2] / "data" / "reference" / "entries.json"
FLAGS = re.I | re.S


@dataclass(frozen=True)
class Entry:
    id: str
    region: str
    publisher: str
    checked: str
    source: str
    claim: str
    tactic: str
    strength: str
    needs: frozenset
    unless: re.Pattern | None
    variants: tuple  # each a tuple of compiled patterns that must ALL match somewhere in the message


@lru_cache(maxsize=1)
def entries() -> tuple[Entry, ...]:
    out = []
    for e in json.loads(PATH.read_text(encoding="utf-8"))["entries"]:
        variants = tuple(tuple((Z(p, FLAGS) if v.get("zh") else re.compile(p, FLAGS)) for p in v["all"]) for v in e["variants"])
        out.append(Entry(e["id"], e["region"], e["publisher"], e["checked"], e["source"], e["claim"], e["tactic"], e["strength"], frozenset(e["needs"]),
                         re.compile(e["unless"], FLAGS) if e.get("unless") else None, variants))
    return tuple(out)


def matches(text: str, asks: set[str], link_unverified: bool = False) -> list[tuple[Entry, str]]:
    """[(entry, the words of the message that matched)] for every listed script this message follows."""
    out = []
    for e in entries():
        if e.unless is not None and e.unless.search(text):
            continue
        if not (e.needs & asks or ("link_unverified" in e.needs and link_unverified)):
            continue
        for v in e.variants:
            hits = [p.search(text) for p in v]
            if all(hits):
                out.append((e, hits[0].group(0).strip()[:80]))
                break
    return out
