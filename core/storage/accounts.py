"""Accounts without emails or passwords. A visitor is already a profile (a cookie id); an account adds a nickname, an avatar, a short code friends use to
find them, and a sign-in key that is shown once and kept only as a hash. Signing in on another device means presenting the key: that device then
takes over the profile, so records, practice and score come along. No message text is ever stored here. Lives in the SHARED database, because friends
are different profiles. A friend is added by their code or invite link (an invitation they chose to share), and either side can end it.
A profile id is the visitor's session cookie: it never leaves this module's callers. Other people see only `pub`, a separate random id."""
from __future__ import annotations

import hashlib
import re
import secrets
import time

from core.storage import db

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I: easy to read out or retype
CODE_LEN = 6
KEY_GROUPS, KEY_GROUP_LEN = 4, 4  # a key like K7M2-QX9P-R4TW-H8NB: 16 characters of 32 = 80 bits, far too many to guess
AVATARS = ("🐟", "🦊", "🐼", "🐯", "🐸", "🦉", "🐙", "🐢", "🦄", "🐳", "🐧", "🦁")
MAX_FRIENDS = 50
NAME_MIN, NAME_MAX = 2, 16
_NAME_OK = re.compile(r"[\w \-]+", re.UNICODE)  # letters (any script), digits, underscore, space, hyphen: no dots, slashes or @, so a name is never a web address


class AccountError(ValueError):
    """The message is plain language, shown to the person (and translated by the website)."""


def clean_name(raw: str) -> str:
    name = re.sub(r"\s+", " ", (raw or "").strip())
    if not (NAME_MIN <= len(name) <= NAME_MAX) or not _NAME_OK.fullmatch(name):
        raise AccountError("Pick a nickname of 2 to 16 letters or numbers.")  # (a constant, so it can be translated)
    return name


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _normal_key(raw: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (raw or "").upper())


def _new_key() -> str:
    chars = "".join(secrets.choice(ALPHABET) for _ in range(KEY_GROUPS * KEY_GROUP_LEN))
    return "-".join(chars[i:i + KEY_GROUP_LEN] for i in range(0, len(chars), KEY_GROUP_LEN))


def _new_code(c) -> str:
    while True:
        code = "".join(secrets.choice(ALPHABET) for _ in range(CODE_LEN))
        if not c.execute("SELECT 1 FROM accounts WHERE friend_code=?", (code,)).fetchone():
            return code


def _own(r) -> dict | None:
    """Your own account, as you may see it (your friend code and creation date included)."""
    return None if r is None else {"pub": r["pub"], "nickname": r["nickname"], "avatar": r["avatar"], "friend_code": r["friend_code"], "created": r["created"]}


def _card(r) -> dict | None:
    """What other people may see of an account: a nickname, an avatar and a public id. Never the profile id, the code or the key."""
    return None if r is None else {"pub": r["pub"], "nickname": r["nickname"], "avatar": r["avatar"]}


def _clean_code(code: str) -> str:
    code = (code or "").strip().upper().replace(" ", "")
    return code if len(code) == CODE_LEN and all(ch in ALPHABET for ch in code) else ""


def get(profile: str) -> dict | None:
    with db.connect(shared=True) as c:
        return _own(c.execute("SELECT * FROM accounts WHERE profile=?", (profile,)).fetchone())


def invite_card(code: str) -> dict | None:
    """Who a friend code or invite link belongs to (just their card), or None."""
    code = _clean_code(code)
    if not code:
        return None
    with db.connect(shared=True) as c:
        return _card(c.execute("SELECT * FROM accounts WHERE friend_code=?", (code,)).fetchone())


def create(profile: str, nickname: str, avatar: str = "") -> tuple[dict, str]:
    """Turn this profile into an account. Returns it and the sign-in key, which is not stored and cannot be shown again."""
    name = clean_name(nickname)
    avatar = avatar if avatar in AVATARS else secrets.choice(AVATARS)
    key = _new_key()
    with db.connect(shared=True) as c:
        if c.execute("SELECT 1 FROM accounts WHERE profile=?", (profile,)).fetchone():
            raise AccountError("You already have a profile.")
        c.execute("INSERT INTO accounts(profile,pub,nickname,avatar,friend_code,key_hash,created) VALUES(?,?,?,?,?,?,?)",
                  (profile, secrets.token_hex(6), name, avatar, _new_code(c), _hash(key), db.iso(db.now())))
    return get(profile), key


def update(profile: str, nickname: str | None = None, avatar: str | None = None) -> dict:
    acct = get(profile)
    if acct is None:
        raise AccountError("Create your profile first.")
    name = clean_name(nickname) if nickname is not None else acct["nickname"]
    avatar = avatar if avatar in AVATARS else acct["avatar"]
    with db.connect(shared=True) as c:
        c.execute("UPDATE accounts SET nickname=?, avatar=? WHERE profile=?", (name, avatar, profile))
    return get(profile)


def new_key(profile: str) -> str:
    """A new sign-in key; the old one stops working at once (use it if a key is lost or seen by someone else)."""
    if get(profile) is None:
        raise AccountError("Create your profile first.")
    key = _new_key()
    with db.connect(shared=True) as c:
        c.execute("UPDATE accounts SET key_hash=? WHERE profile=?", (_hash(key), profile))
    return key


def new_friend_code(profile: str) -> str:
    """A new code to share; the old code and invite link stop working (friends you already have are kept)."""
    with db.connect(shared=True) as c:
        if not c.execute("SELECT 1 FROM accounts WHERE profile=?", (profile,)).fetchone():
            raise AccountError("Create your profile first.")
        code = _new_code(c)
        c.execute("UPDATE accounts SET friend_code=? WHERE profile=?", (code, profile))
    return code


# sign-in tries are counted per client by the website; this is the second lock, for an attacker who has many addresses: a slow global cap
_TRIES: list[float] = []
GLOBAL_TRIES_PER_MINUTE = 60


def sign_in(key: str) -> str | None:
    """The profile this key belongs to, or None."""
    now = time.monotonic()
    while _TRIES and now - _TRIES[0] > 60:
        _TRIES.pop(0)
    if len(_TRIES) >= GLOBAL_TRIES_PER_MINUTE:
        return None
    _TRIES.append(now)
    k = _normal_key(key)
    if len(k) != KEY_GROUPS * KEY_GROUP_LEN or any(ch not in ALPHABET for ch in k):
        return None
    dashed = "-".join(k[i:i + KEY_GROUP_LEN] for i in range(0, len(k), KEY_GROUP_LEN))
    with db.connect(shared=True) as c:
        r = c.execute("SELECT profile FROM accounts WHERE key_hash=?", (_hash(dashed),)).fetchone()
    return r["profile"] if r else None


def delete(profile: str) -> None:
    """Remove the account, its friendships and its game runs. (The profile's own records and practice are deleted from the Records page.)"""
    with db.connect(shared=True) as c:
        c.execute("DELETE FROM accounts WHERE profile=?", (profile,))
        c.execute("DELETE FROM friendships WHERE a=? OR b=?", (profile, profile))
        c.execute("DELETE FROM runs WHERE profile=?", (profile,))
        c.execute("DELETE FROM push_subs WHERE profile=?", (profile,))


# ---------------------------------------------------------------- friends
def add_friend(me: str, code: str) -> dict:
    """Befriend whoever owns this code: mutual at once, because they chose to share the code. Returns their card."""
    clean = _clean_code(code)
    with db.connect(shared=True) as c:
        other = c.execute("SELECT * FROM accounts WHERE friend_code=?", (clean,)).fetchone() if clean else None
        if other is None:
            raise AccountError("That friend code doesn't match anyone. Check it and try again.")
        if other["profile"] == me:
            raise AccountError("That's your own code. Send it to a friend instead.")
        if not c.execute("SELECT 1 FROM accounts WHERE profile=?", (me,)).fetchone():
            raise AccountError("Create your profile first.")
        if c.execute("SELECT 1 FROM friendships WHERE a=? AND b=?", (me, other["profile"])).fetchone():
            raise AccountError("You are already friends.")
        if any(c.execute("SELECT COUNT(*) AS n FROM friendships WHERE a=?", (p,)).fetchone()["n"] >= MAX_FRIENDS for p in (me, other["profile"])):
            raise AccountError("Friend lists are full at 50 friends.")
        ts = db.iso(db.now())
        c.execute("INSERT INTO friendships(a,b,since) VALUES(?,?,?)", (me, other["profile"], ts))
        c.execute("INSERT INTO friendships(a,b,since) VALUES(?,?,?)", (other["profile"], me, ts))
    return _card(other)


def remove_friend(me: str, pub: str) -> bool:
    """End a friendship (either side may), naming the friend by their public id. True if there was one."""
    with db.connect(shared=True) as c:
        other = c.execute("SELECT profile FROM accounts WHERE pub=?", (pub,)).fetchone()
        if other is None:
            return False
        n = c.execute("DELETE FROM friendships WHERE (a=? AND b=?) OR (a=? AND b=?)", (me, other["profile"], other["profile"], me)).rowcount
    return n > 0


def friends(me: str) -> list[dict]:
    with db.connect(shared=True) as c:
        rows = c.execute("SELECT a2.* FROM friendships f JOIN accounts a2 ON a2.profile=f.b WHERE f.a=? ORDER BY lower(a2.nickname)", (me,)).fetchall()
    return [_card(r) for r in rows]
