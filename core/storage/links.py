"""Link a Telegram chat to a web profile, with no accounts: the web page shows a short one-time code (or a t.me link that carries it, so the person only taps Start), the bot gets it, and
from then on that chat's checks land in the same profile (same records, same practice, same score). Lives in the SHARED database, because
the web app and the bot are separate processes."""
from __future__ import annotations

import secrets
import time

from core.storage import db

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I: easy to read out or retype
CODE_LEN = 6
TTL = 600.0  # seconds
LOCAL = "local"  # the one profile of a single-user (non-multiuser) install


def current_profile() -> str:
    """The profile of whoever is making this request: their cookie id, or 'local' on a single-user install."""
    return db._profile.get() or LOCAL if db.multiuser() else LOCAL


def new_code(profile: str) -> str:
    """A fresh one-time code for this profile. Any earlier unused code of theirs stops working."""
    code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LEN))
    with db.connect(shared=True) as c:
        c.execute("DELETE FROM link_codes WHERE profile=? AND used=0", (profile,))
        c.execute("DELETE FROM link_codes WHERE created < ?", (time.time() - 3600,))
        c.execute("INSERT INTO link_codes(code,profile,created,used) VALUES(?,?,?,0)", (code, profile, time.time()))
    return code


def redeem(code: str, chat_id: int | str) -> str | None:
    """Spend a code for this chat. Returns the profile it now belongs to, or None (wrong, expired or already used)."""
    code = (code or "").strip().upper().replace(" ", "")
    if len(code) != CODE_LEN or any(ch not in ALPHABET for ch in code):
        return None
    with db.connect(shared=True) as c:
        row = c.execute("SELECT * FROM link_codes WHERE code=? AND used=0", (code,)).fetchone()
        if not row or time.time() - row["created"] > TTL:
            return None
        c.execute("UPDATE link_codes SET used=1 WHERE code=?", (code,))
        c.execute("INSERT INTO telegram_links(chat_id,profile,linked_at) VALUES(?,?,?) ON CONFLICT(chat_id) DO UPDATE SET profile=excluded.profile, linked_at=excluded.linked_at",
                  (str(chat_id), row["profile"], db.iso(db.now())))
    return row["profile"]


def peek(code: str) -> str | None:
    """The profile a code belongs to, if it is still good, without spending it (the bot looks before it links)."""
    code = (code or "").strip().upper().replace(" ", "")
    if len(code) != CODE_LEN or any(ch not in ALPHABET for ch in code):
        return None
    with db.connect(shared=True) as c:
        row = c.execute("SELECT * FROM link_codes WHERE code=? AND used=0", (code,)).fetchone()
    return row["profile"] if row and time.time() - row["created"] <= TTL else None


def profile_for_chat(chat_id: int | str) -> str | None:
    with db.connect(shared=True) as c:
        r = c.execute("SELECT profile FROM telegram_links WHERE chat_id=?", (str(chat_id),)).fetchone()
    return r["profile"] if r else None


def chats_for(profile: str) -> int:
    with db.connect(shared=True) as c:
        return c.execute("SELECT COUNT(*) AS n FROM telegram_links WHERE profile=?", (profile,)).fetchone()["n"]


def unlink_profile(profile: str) -> int:
    with db.connect(shared=True) as c:
        return c.execute("DELETE FROM telegram_links WHERE profile=?", (profile,)).rowcount


def unlink_chat(chat_id: int | str) -> bool:
    with db.connect(shared=True) as c:
        return c.execute("DELETE FROM telegram_links WHERE chat_id=?", (str(chat_id),)).rowcount > 0
