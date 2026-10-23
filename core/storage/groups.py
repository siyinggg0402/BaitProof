"""Family groups: parents and kids (or any small family) who share a bank of scams and a leaderboard. A member can choose to share a scam they met: only the
REDACTED example the library already keeps (phone numbers, e-mails and link paths removed), never the message they received, and they see exactly what is
shared. Shared scams become gates in the others' games ("From your family"). One group per person, up to a dozen people; the owner can remove members,
anyone can leave. Lives in the SHARED database. A profile id is a session cookie: it never leaves this module's callers (members are shown as cards)."""
from __future__ import annotations

import json
import re
import secrets
from datetime import timedelta

from core.storage import accounts, db, library

MAX_MEMBERS = 12
MAX_SCAMS = 60
RECENT = timedelta(minutes=20)  # "share the one I just checked" means a check from the last twenty minutes
ALPHABET = accounts.ALPHABET


class GroupError(ValueError):
    """The message is plain language, shown to the person (and translated by the website)."""


def clean_name(raw: str) -> str:
    name = re.sub(r"\s+", " ", (raw or "").strip())
    if not (2 <= len(name) <= 24) or not accounts._NAME_OK.fullmatch(name):
        raise GroupError("Pick a family name of 2 to 24 letters or numbers.")
    return name


def _code(c) -> str:
    while True:
        code = "".join(secrets.choice(ALPHABET) for _ in range(6))
        if not c.execute("SELECT 1 FROM family_groups WHERE code=?", (code,)).fetchone():
            return code


def _group_of(c, profile: str):
    return c.execute("SELECT g.* FROM family_groups g JOIN family_members m ON m.group_id=g.id WHERE m.profile=?", (profile,)).fetchone()


def _need_account(profile: str) -> None:
    if accounts.get(profile) is None:
        raise GroupError("Create your profile first.")


def create(profile: str, name: str, share: bool = True) -> dict:
    _need_account(profile)
    name = clean_name(name)
    with db.connect(shared=True) as c:
        if _group_of(c, profile):
            raise GroupError("You are already in a family group. Leave it first to start another.")
        gid = secrets.token_hex(6)
        ts = db.iso(db.now())
        c.execute("INSERT INTO family_groups(id,name,code,owner,created) VALUES(?,?,?,?,?)", (gid, name, _code(c), profile, ts))
        c.execute("INSERT INTO family_members(group_id,profile,since,share) VALUES(?,?,?,?)", (gid, profile, ts, int(share)))
    return of(profile)


def by_code(code: str) -> dict | None:
    """What an invite shows before anyone joins: the family's name and how many are in it."""
    code = (code or "").strip().upper().replace(" ", "")
    if len(code) != 6 or any(ch not in ALPHABET for ch in code):
        return None
    with db.connect(shared=True) as c:
        g = c.execute("SELECT * FROM family_groups WHERE code=?", (code,)).fetchone()
        if g is None:
            return None
        return {"name": g["name"], "members": c.execute("SELECT COUNT(*) AS n FROM family_members WHERE group_id=?", (g["id"],)).fetchone()["n"]}


def join(profile: str, code: str, share: bool = True) -> dict:
    _need_account(profile)
    code = (code or "").strip().upper().replace(" ", "")
    with db.connect(shared=True) as c:
        g = c.execute("SELECT * FROM family_groups WHERE code=?", (code,)).fetchone() if len(code) == 6 else None
        if g is None:
            raise GroupError("That family code doesn't match a group. Check it and try again.")
        if _group_of(c, profile):
            raise GroupError("You are already in a family group. Leave it first to join another.")
        if c.execute("SELECT COUNT(*) AS n FROM family_members WHERE group_id=?", (g["id"],)).fetchone()["n"] >= MAX_MEMBERS:
            raise GroupError("That family group is full.")
        c.execute("INSERT INTO family_members(group_id,profile,since,share) VALUES(?,?,?,?)", (g["id"], profile, db.iso(db.now()), int(share)))
    return of(profile)


def of(profile: str) -> dict | None:
    """The group this person is in, as they may see it: members (cards), shared scams, and the invite code only for them."""
    with db.connect(shared=True) as c:
        g = _group_of(c, profile)
        if g is None:
            return None
        members = c.execute("SELECT a.pub, a.nickname, a.avatar, m.profile, m.share FROM family_members m JOIN accounts a ON a.profile=m.profile WHERE m.group_id=? ORDER BY m.since", (g["id"],)).fetchall()
        scams = c.execute("SELECT s.id, s.text, s.tactics, s.created, s.by_profile, a.nickname AS by_name FROM family_scams s LEFT JOIN accounts a ON a.profile=s.by_profile WHERE s.group_id=? ORDER BY s.id DESC", (g["id"],)).fetchall()
    return {"name": g["name"], "code": g["code"], "is_owner": g["owner"] == profile,
            "members": [{"pub": m["pub"], "nickname": m["nickname"], "avatar": m["avatar"], "owner": m["profile"] == g["owner"], "you": m["profile"] == profile, "shares": bool(m["share"])} for m in members],
            "you_share": any(m["share"] for m in members if m["profile"] == profile),
            "scams": [{"id": s["id"], "text": s["text"], "tactics": json.loads(s["tactics"]), "by": s["by_name"] or "", "mine": s["by_profile"] == profile} for s in scams]}


def name_of(profile: str) -> str:
    with db.connect(shared=True) as c:
        g = _group_of(c, profile)
    return g["name"] if g else ""


def member_profiles(profile: str) -> list[str]:
    """INTERNAL: the profile ids of everyone in this person's group (for a ranking). Never for a browser."""
    with db.connect(shared=True) as c:
        g = _group_of(c, profile)
        if g is None:
            return []
        return [r["profile"] for r in c.execute("SELECT profile FROM family_members WHERE group_id=?", (g["id"],)).fetchall()]


def leave(profile: str) -> None:
    """Leave the group. An owner who leaves hands it to the person who has been in it longest; the last person out closes it."""
    with db.connect(shared=True) as c:
        g = _group_of(c, profile)
        if g is None:
            return
        c.execute("DELETE FROM family_members WHERE group_id=? AND profile=?", (g["id"], profile))
        rest = c.execute("SELECT profile FROM family_members WHERE group_id=? ORDER BY since", (g["id"],)).fetchall()
        if not rest:
            c.execute("DELETE FROM family_groups WHERE id=?", (g["id"],))
            c.execute("DELETE FROM family_scams WHERE group_id=?", (g["id"],))
        elif g["owner"] == profile:
            c.execute("UPDATE family_groups SET owner=? WHERE id=?", (rest[0]["profile"], g["id"]))


def delete(profile: str) -> None:
    with db.connect(shared=True) as c:
        g = _group_of(c, profile)
        if g is None or g["owner"] != profile:
            raise GroupError("Only the person who started the group can close it.")
        for t in ("family_members", "family_scams"):
            c.execute(f"DELETE FROM {t} WHERE group_id=?", (g["id"],))
        c.execute("DELETE FROM family_groups WHERE id=?", (g["id"],))


def remove_member(owner: str, pub: str) -> bool:
    with db.connect(shared=True) as c:
        g = _group_of(c, owner)
        if g is None or g["owner"] != owner:
            raise GroupError("Only the person who started the group can remove someone.")
        other = c.execute("SELECT m.profile FROM family_members m JOIN accounts a ON a.profile=m.profile WHERE m.group_id=? AND a.pub=?", (g["id"], pub)).fetchone()
        if other is None or other["profile"] == owner:
            return False
        c.execute("DELETE FROM family_members WHERE group_id=? AND profile=?", (g["id"], other["profile"]))
    return True


def new_code(owner: str) -> str:
    with db.connect(shared=True) as c:
        g = _group_of(c, owner)
        if g is None or g["owner"] != owner:
            raise GroupError("Only the person who started the group can change its code.")
        code = _code(c)
        c.execute("UPDATE family_groups SET code=? WHERE id=?", (code, g["id"]))
    return code


# ---------------------------------------------------------------- the shared bank of scams
def share(profile: str, ex: str) -> dict:
    """Share one of this person's own library examples ("u12", or "latest": the newest, if it is recent) with their family. Returns what was shared."""
    examples = library.user_examples()
    if ex == "latest":
        with db.connect() as c:
            row = c.execute("SELECT id, created FROM library ORDER BY id DESC LIMIT 1").fetchone()
        if row is None or db.parse(row["created"]) is None or db.now() - db.parse(row["created"]) > RECENT:
            raise GroupError("There is nothing recent to share. Check the message again first.")
        ex = f"u{row['id']}"
    item = next((e for e in examples if e["id"] == ex), None)
    if item is None:
        raise GroupError("That scam isn't in your list any more.")
    with db.connect(shared=True) as c:
        g = _group_of(c, profile)
        if g is None:
            raise GroupError("Start or join a family group first.")
        try:
            c.execute("INSERT INTO family_scams(group_id,text,tactics,tell_phrase,tell,action,by_profile,created) VALUES(?,?,?,?,?,?,?,?)",
                      (g["id"], item["text"], json.dumps(item["tactics"]), item["tell_phrase"], item["tell"], item["action"], profile, db.iso(db.now())))
        except Exception:  # (the same text already shared: nothing to do twice)
            raise GroupError("Your family already has that one.") from None
        extra = c.execute("SELECT COUNT(*) AS n FROM family_scams WHERE group_id=?", (g["id"],)).fetchone()["n"] - MAX_SCAMS
        if extra > 0:  # the bank keeps the newest sixty
            c.execute("DELETE FROM family_scams WHERE id IN (SELECT id FROM family_scams WHERE group_id=? ORDER BY id LIMIT ?)", (g["id"], extra))
    return item


def unshare(profile: str, scam_id: int) -> bool:
    """Take a scam back out: by whoever shared it, or by the group's owner."""
    with db.connect(shared=True) as c:
        g = _group_of(c, profile)
        if g is None:
            return False
        s = c.execute("SELECT by_profile FROM family_scams WHERE id=? AND group_id=?", (scam_id, g["id"])).fetchone()
        if s is None or (s["by_profile"] != profile and g["owner"] != profile):
            return False
        c.execute("DELETE FROM family_scams WHERE id=?", (scam_id,))
    return True


def scams_for(profile: str) -> list[dict]:
    """The shared scams of this person's family, in the shape of library examples, for the games."""
    with db.connect(shared=True) as c:
        g = _group_of(c, profile)
        if g is None:
            return []
        rows = c.execute("SELECT * FROM family_scams WHERE group_id=? ORDER BY id DESC", (g["id"],)).fetchall()
    return [{"id": f"f{r['id']}", "text": r["text"], "tactics": json.loads(r["tactics"]), "tell_phrase": r["tell_phrase"], "tell": r["tell"], "action": r["action"]} for r in rows]


def set_share(profile: str, on: bool) -> None:
    """Choose whether the family can see your practice progress (your score, streak and which tricks you have practised: never messages)."""
    with db.connect(shared=True) as c:
        c.execute("UPDATE family_members SET share=? WHERE profile=?", (int(on), profile))


def members_for_dashboard(profile: str) -> list[dict]:
    """INTERNAL: everyone in this person's group as {profile id, card, owner, shares}, for the dashboard to read the progress of those who share. Never for a browser."""
    with db.connect(shared=True) as c:
        g = _group_of(c, profile)
        if g is None:
            return []
        rows = c.execute("SELECT m.profile, m.share, a.pub, a.nickname, a.avatar FROM family_members m JOIN accounts a ON a.profile=m.profile WHERE m.group_id=? ORDER BY m.since", (g["id"],)).fetchall()
        week = db.iso(db.now() - timedelta(days=7))
        shared_week = c.execute("SELECT COUNT(*) AS n FROM family_scams WHERE group_id=? AND created>=?", (g["id"], week)).fetchone()["n"]
    return [{"profile": r["profile"], "pub": r["pub"], "nickname": r["nickname"], "avatar": r["avatar"], "owner": r["profile"] == g["owner"], "shares": bool(r["share"]),
             "you": r["profile"] == profile, "family": g["name"], "shared_week": shared_week} for r in rows]
