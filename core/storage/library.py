"""Threat library: curated seed bank + the user's own ABSTRACTED examples (never raw PII)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

from core.storage import db
from core.domain.tactics import valid

SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "seed_examples.json"

URL_RE = re.compile(r"(?:https?://|www\.)[^\s]+|\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|net|org|xyz|top|click|info|icu|co|io|me|ly|shop|site|online)(?:/[^\s]*)?", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{6,}\d")


def host_of(url: str) -> str:
    u = url if "//" in url else "//" + url
    return (urlparse(u).hostname or url).lower().rstrip(".,)")


def redact(text: str, links: bool = True) -> str:
    """Deterministic PII scrub. URLs shrink to bare host (scam domains aren't personal; paths/tokens may be)."""
    text = EMAIL_RE.sub("[email]", text)
    text = URL_RE.sub(lambda m: host_of(m.group(0)), text)
    text = PHONE_RE.sub("[number]", text)
    return text.strip()


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
