"""Family alerts, by consent on both sides and with no accounts.

The person being protected sends /family to the bot and gets a short one-time code. Someone they trust (a son, a daughter) sends /guard CODE in their own chat.
From then on, when the protected person checks something that looks like a scam, the helper gets a short note: that they checked one, and which tricks it uses.
The helper NEVER receives the message, its words or the link. Either side can stop it at any time. Lives in the SHARED database (the helper's chat and the
protected person's chat are different profiles)."""
from __future__ import annotations

import re
import secrets
import time

from core.storage import db

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LEN = 6
TTL = 600.0
MAX_HELPERS = 5  # per protected person
MAX_ALERTS_PER_HOUR = 6  # per protected person: a flurry of scams must not become a flood
_NAME = re.compile(r"[^\w .'-]+", re.UNICODE)
_sent: dict[str, list[float]] = {}


def clean_name(raw: str) -> str:
    """How the helper will see the protected person: a short plain name ('Mum'), nothing else."""
    return " ".join(_NAME.sub(" ", raw or "").split())[:24]


def new_code(profile: str, chat_id: int | str, name: str = "") -> str:
    """A fresh one-time invite for this protected person. An earlier unused one of theirs stops working."""
    code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LEN))
    with db.connect(shared=True) as c:
        c.execute("DELETE FROM guard_codes WHERE profile=? AND used=0", (profile,))
        c.execute("DELETE FROM guard_codes WHERE created < ?", (time.time() - 3600,))
        c.execute("INSERT INTO guard_codes(code,profile,chat_id,name,created,used) VALUES(?,?,?,?,?,0)", (code, profile, str(chat_id), clean_name(name), time.time()))
    return code


def redeem(code: str, helper_chat: int | str, lang: str) -> dict | None:
    """The helper spends a code. Returns {profile, name, owner_chat} or None (wrong, expired, used, or too many helpers already)."""
    code = (code or "").strip().upper().replace(" ", "")
    if len(code) != CODE_LEN or any(ch not in ALPHABET for ch in code):
        return None
    with db.connect(shared=True) as c:
        row = c.execute("SELECT * FROM guard_codes WHERE code=? AND used=0", (code,)).fetchone()
        if not row or time.time() - row["created"] > TTL or str(helper_chat) == row["chat_id"]:  # (you cannot be your own helper)
            return None
        if c.execute("SELECT COUNT(*) AS n FROM guardians WHERE profile=?", (row["profile"],)).fetchone()["n"] >= MAX_HELPERS:
            return None
        c.execute("UPDATE guard_codes SET used=1 WHERE code=?", (code,))
        c.execute("INSERT INTO guardians(chat_id,profile,name,lang,since) VALUES(?,?,?,?,?) ON CONFLICT(chat_id,profile) DO UPDATE SET name=excluded.name, lang=excluded.lang",
                  (str(helper_chat), row["profile"], row["name"], lang, db.iso(db.now())))
    return {"profile": row["profile"], "name": row["name"], "owner_chat": row["chat_id"]}


def helpers_of(profile: str) -> list[dict]:
    with db.connect(shared=True) as c:
        return [dict(r) for r in c.execute("SELECT chat_id,name,lang FROM guardians WHERE profile=?", (profile,)).fetchall()]


def count(profile: str) -> int:
    with db.connect(shared=True) as c:
        return c.execute("SELECT COUNT(*) AS n FROM guardians WHERE profile=?", (profile,)).fetchone()["n"]


def stop_for_owner(profile: str) -> list[dict]:
    """The protected person turns it off: every helper is removed. Returns who they were (so they can be told)."""
    gone = helpers_of(profile)
    with db.connect(shared=True) as c:
        c.execute("DELETE FROM guardians WHERE profile=?", (profile,))
        c.execute("DELETE FROM guard_codes WHERE profile=?", (profile,))
    return gone


def stop_for_helper(chat_id: int | str) -> list[dict]:
    """A helper leaves: they are removed from everyone they were helping. Returns {profile, name, owner_chat?} for each (the owner is not told who left)."""
    with db.connect(shared=True) as c:
        rows = [dict(r) for r in c.execute("SELECT profile,name FROM guardians WHERE chat_id=?", (str(chat_id),)).fetchall()]
        c.execute("DELETE FROM guardians WHERE chat_id=?", (str(chat_id),))
    return rows


def may_alert(profile: str) -> bool:
    """False once this person has already caused MAX_ALERTS_PER_HOUR alerts in the last hour."""
    now = time.time()
    sent = [t for t in _sent.get(profile, []) if now - t < 3600]
    if len(sent) >= MAX_ALERTS_PER_HOUR:
        _sent[profile] = sent
        return False
    sent.append(now)
    _sent[profile] = sent
    return True
