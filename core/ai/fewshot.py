"""Dynamic few-shot: instead of showing every message the same fixed examples, retrieve the labelled examples MOST SIMILAR to this
message and show those. A premium-rate text meets premium-rate examples; a "your card is blocked" alarm meets alarm examples.
The bank is (a) a hand-authored reference file and (b) the scams the user's own circle forwarded (the flywheel's threat library),
so the checker also learns the scams going round YOUR family. Similarity is plain TF-IDF: no network, no model call, deterministic."""
from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

BANK_PATH = Path(__file__).resolve().parents[2] / "data" / "fewshot" / "bank.json"
SCAMMY = ("scam", "likely_scam")
MIN_SIM = 0.08
URL = re.compile(r"(?:https?://|www\.)?[a-z0-9-]+(?:\.[a-z0-9-]+)*\.([a-z]{2,10})(?:/\S*)?", re.I)
WORD = re.compile(r"[a-z0-9£$€%]+")


@dataclass
class Example:
    id: str
    text: str
    verdict: str
    purpose: str = ""
    tactics: list[str] = field(default_factory=list)
    why: str = ""
    source: str = "authored"  # authored | library


def enabled() -> bool:
    """Off by default until a measurement says it helps (see docs/EVALUATION.md). BAITPROOF_FEWSHOT=1 turns it on."""
    return os.getenv("BAITPROOF_FEWSHOT", "0") == "1"


def features(text: str) -> list[str]:
    """Words and word pairs, with numbers / links / short codes normalised so structure matches rather than the exact digits."""
    t = text.lower()
    t = URL.sub(lambda m: f" urlx tld{m.group(1)} ", t) if "." in t else t
    t = re.sub(r"\b\d+(?:\.\d+)?\s?p(?:pm)?\b|\bppm\b|\bper (?:min|minute|msg|message|text|week|wk)\b|\b[£$€]\s?\d+(?:\.\d{2})?\s?(?:/|per)\s?(?:msg|min|text|wk|week)\b", " pricex ", t)  # premium-rate prices
    t = re.sub(r"\b\d{9,}\b|\b0\d{9,10}\b", " phonex ", t)
    t = re.sub(r"\b\d{4,6}\b", " shortcodex ", t)
    t = re.sub(r"\d+(?:[.,]\d+)?", " numx ", t)
    words = WORD.findall(t)
    return words + [a + "_" + b for a, b in zip(words, words[1:])]


def load_authored() -> list[Example]:
    return [Example(source="authored", **e) for e in json.loads(BANK_PATH.read_text(encoding="utf-8"))]


def load_library() -> list[Example]:
    """The scams this user's own circle forwarded and the checker confirmed (already abstracted, no raw PII)."""
    try:
        from core.storage import library

        return [Example(id=str(e["id"]), text=e["text"], verdict="scam", tactics=list(e["tactics"]), why=(e.get("tell") or "")[:140], source="library")
                for e in library.user_examples()]
    except Exception:  # the bank must never break a check
        return []


class Index:
    def __init__(self, examples: list[Example]) -> None:
        self.examples = examples
        docs = [Counter(features(e.text)) for e in examples]
        df = Counter(tok for d in docs for tok in d)
        n = len(docs)
        self.idf = {tok: math.log((1 + n) / (1 + c)) + 1 for tok, c in df.items()}
        self.vecs = [self._vec(d) for d in docs]

    def _vec(self, counts: Counter) -> dict[str, float]:
        v = {t: (1 + math.log(c)) * self.idf.get(t, 0.0) for t, c in counts.items() if t in self.idf}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norm for t, x in v.items()}

    def scored(self, text: str) -> list[tuple[float, Example]]:
        q = self._vec(Counter(features(text)))
        out = [(sum(w * v.get(t, 0.0) for t, w in q.items()), e) for v, e in zip(self.vecs, self.examples)]
        return sorted(out, key=lambda x: -x[0])


_cache: dict = {"sig": None, "index": None}


def _index() -> Index:
    lib = load_library()
    sig = (len(lib), lib[0].id if lib else "")
    if _cache["sig"] != sig:
        _cache.update(sig=sig, index=Index(load_authored() + lib))
    return _cache["index"]


def mode() -> str:
    """'balanced' (default): show as many genuine neighbours as scam neighbours. 'knn': plain nearest neighbours, which copies the bank's
    own mix of labels (measured: it lifted recall but also false alarms on genuine financial notices)."""
    return os.getenv("BAITPROOF_FEWSHOT_MODE", "balanced")


def retrieve(text: str, k: int = 4) -> list[Example]:
    """Top-k most similar labelled examples, never the message itself, and never all on one side of the verdict when the other side
    has something relevant (a calibration aid: the model should see what the genuine version of a similar message looks like too)."""
    norm = " ".join(text.lower().split())
    ranked = [(s, e) for s, e in _index().scored(text) if " ".join(e.text.lower().split()) != norm and s >= MIN_SIM]
    if mode() == "balanced":
        scammy = [x for x in ranked if x[1].verdict in SCAMMY][: k // 2]
        benign = [x for x in ranked if x[1].verdict not in SCAMMY][: k // 2]
        picked = sorted(scammy + benign, key=lambda x: -x[0])
        if scammy and benign:
            return [e for _, e in picked]
        # only one side is relevant: fall through to plain nearest neighbours rather than showing irrelevant examples of the other side
    top = ranked[:k]
    if len(top) == k and len({e.verdict in SCAMMY for _, e in top}) == 1:
        want_scam = not (top[-1][1].verdict in SCAMMY)
        other = next(((s, e) for s, e in ranked[k:k + 10] if (e.verdict in SCAMMY) == want_scam and s >= MIN_SIM * 0.6), None)
        if other:
            top[-1] = other
    return [e for _, e in top]


def block(examples: list[Example]) -> str:
    if not examples:
        return ""
    lines = []
    for e in examples:
        tricks = ", ".join(e.tactics) if e.tactics else "none"
        lines.append(f'- "{e.text[:200]}" -> {e.verdict} | {e.purpose or "n/a"} | {tricks}' + (f" ({e.why})" if e.why else ""))
    return ("SIMILAR LABELLED EXAMPLES (from our reference library; use them to calibrate, but judge the new message on its own words):\n" + "\n".join(lines))
