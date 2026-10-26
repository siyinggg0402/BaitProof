"""Shareable 'Can you spot the scam?' challenge. No accounts; does not touch the personal model."""
from __future__ import annotations

import json
import random
import uuid

from core.storage import db
from core.storage import library


def create(n: int = 6, lang: str = "en") -> str:
    ex = library.all_examples(lang)
    scams = [e for e in ex if e["is_scam"]]
    legit = [e for e in ex if not e["is_scam"]]
    user = [e for e in scams if e["source"] == "user"]
    picked = random.sample(user, min(2, len(user)))
    rest = [e for e in scams if e not in picked]
    n_legit = min(2, len(legit))
    picked += random.sample(rest, min(n - n_legit - len(picked), len(rest))) + random.sample(legit, n_legit)
    random.shuffle(picked)
    items = [{"text": e["text"], "is_scam": e["is_scam"], "tell": e["tell"]} for e in picked]
    cid = uuid.uuid4().hex[:8]
    with db.connect(shared=True) as c:
        c.execute("INSERT INTO challenges(id,items,created) VALUES(?,?,?)", (cid, json.dumps(items), db.iso(db.now())))
    return cid


def get(cid: str) -> list[dict] | None:
    with db.connect(shared=True) as c:
        r = c.execute("SELECT items FROM challenges WHERE id=?", (cid,)).fetchone()
    return json.loads(r["items"]) if r else None


def score(items: list[dict], answers: list[bool | None]) -> dict:
    review = []
    right = 0
    for i, it in enumerate(items):
        a = answers[i] if i < len(answers) else None
        ok = a is not None and a == it["is_scam"]
        right += ok
        review.append({"is_scam": it["is_scam"], "correct": ok, "tell": it["tell"]})
    return {"right": right, "total": len(items), "pct": round(100 * right / max(len(items), 1)), "review": review}
