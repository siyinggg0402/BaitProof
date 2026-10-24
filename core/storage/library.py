"""Threat library: curated seed bank + the user's own ABSTRACTED examples (never raw PII)."""
from __future__ import annotations

import json
from pathlib import Path

from core.domain import privacy
from core.lang import i18n
from core.domain.tactics import valid
from core.storage import db

SEEDS = Path(__file__).resolve().parents[2] / "data" / "seeds"  # one curated bank per language: en.json, zh.json, ms.json

# Re-exported so existing imports keep working; the implementation lives in core.domain.privacy.
URL_RE, EMAIL_RE, PHONE_RE = privacy.URL_RE, privacy.EMAIL_RE, privacy.PHONE_RE
host_of, redact = privacy.host_of, privacy.redact


def seed_examples(lang: str = "en") -> list[dict]:
    """The curated bank for a language. English by default (so every existing caller is unchanged); "zh" is the Simplified Chinese bank and
    "zh-Hant" the same bank converted to Traditional (a phrase that no longer matches after conversion is dropped rather than shown wrong);
    "ms" is the Malay bank and "ta" the Tamil one, written around Malaysian and Singaporean scams."""
    lang = i18n.norm(lang)
    items = json.loads((SEEDS / {"zh": "zh.json", "zh-Hant": "zh.json", "ms": "ms.json", "ta": "ta.json"}.get(lang, "en.json")).read_text(encoding="utf-8"))
    for it in items:
        it["source"] = "seed"
        if lang == "zh-Hant":
            for k in ("text", "tell_phrase", "tell", "action"):
                it[k] = i18n.to_traditional(it[k])
            if it["tell_phrase"] not in it["text"]:
                it["tell_phrase"] = ""
    return items


def user_examples() -> list[dict]:
    with db.connect() as c:
        rows = c.execute("SELECT * FROM library ORDER BY id DESC").fetchall()
    return [
        {"id": f"u{r['id']}", "source": "user", "is_scam": True, "text": r["text"], "tactics": json.loads(r["tactics"]),
         "tell_phrase": r["tell_phrase"], "tell": r["tell"], "action": r["action"]}
        for r in rows
    ]


def all_examples(lang: str = "en") -> list[dict]:
    return user_examples() + seed_examples(lang)


def add_user_example(text: str, tactics: list[str], tell_phrase: str, tell: str, action: str) -> bool:
    """Stores an already-abstracted example. Returns False if empty/duplicate."""
    text = redact(text)[:500]
    tell, action = redact(tell)[:400], redact(action)[:400]  # model-written text can echo names or numbers too
    tactics = [t for t in tactics if valid(t)]
    if not text or not tactics:
        return False
    if tell_phrase not in text:
        tell_phrase = ""
    with db.connect() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO library(text,tactics,tell_phrase,tell,action,created) VALUES(?,?,?,?,?,?)",
            (text, json.dumps(tactics), tell_phrase, tell, action, db.iso(db.now())),
        )
        return cur.rowcount > 0
