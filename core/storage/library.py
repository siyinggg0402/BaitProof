"""Threat library: curated seed bank + the user's own ABSTRACTED examples (never raw PII)."""
from __future__ import annotations

import json
from pathlib import Path

from core.domain import privacy
from core.domain.tactics import valid
from core.storage import db

SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "seed_examples.json"

# Re-exported so existing imports keep working; the implementation lives in core.domain.privacy.
URL_RE, EMAIL_RE, PHONE_RE = privacy.URL_RE, privacy.EMAIL_RE, privacy.PHONE_RE
host_of, redact = privacy.host_of, privacy.redact


def seed_examples() -> list[dict]:
    items = json.loads(SEED_PATH.read_text())
    for it in items:
        it["source"] = "seed"
    return items


def user_examples() -> list[dict]:
    with db.connect() as c:
        rows = c.execute("SELECT * FROM library ORDER BY id DESC").fetchall()
    return [
        {"id": f"u{r['id']}", "source": "user", "is_scam": True, "text": r["text"], "tactics": json.loads(r["tactics"]),
         "tell_phrase": r["tell_phrase"], "tell": r["tell"], "action": r["action"]}
        for r in rows
    ]


def all_examples() -> list[dict]:
    return user_examples() + seed_examples()


def add_user_example(text: str, tactics: list[str], tell_phrase: str, tell: str, action: str) -> bool:
    """Stores an already-abstracted example. Returns False if empty/duplicate."""
    text = redact(text)[:500]
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
