"""Live head-to-head races. Two to four people open the same lobby, the host starts it, a shared countdown runs, and everybody drives the very same twelve gates of Scam
Road at the same time: the most right answers wins, ties go to more hearts left and then to whoever finished first. Each driver is an ordinary server-graded drive
(core/game/road.py) over a fixed length of road, so a score cannot be forged; this module only gathers them into a race: the lobby, the countdown, each driver's live
progress for the others to see (which gates were right, careful or wrong, and when, never an answer), the ranking, the XP and the head-to-head record.

Races live in memory (a restart ends the ones in progress), the browsers poll once a second (so it works behind any proxy), and a driver who stops polling during the
race is counted out after a short while so nobody waits for a closed tab. The messages are read in the host's language."""
from __future__ import annotations

import secrets
from collections import OrderedDict
from dataclasses import dataclass, field

from core.game import road
from core.game import pool as gp
from core.game import state as gs
from core.storage import accounts, db

GATES = 12
MAX_PLAYERS = 4
COUNTDOWN = 4.0          # seconds from "start" to "go"
LOBBY_TTL = 1800.0       # an unstarted lobby closes after half an hour
RACE_MAX = 420.0         # a race that has run this long is over
FORFEIT_AFTER = 45.0     # seconds without hearing from a driver, during the race
MAX_OPEN = 3             # lobbies one person can have open at once
XP_WIN, XP_PLAY = 25, 10
ALPHABET = accounts.ALPHABET


class DuelError(ValueError):
    """The message is plain language, shown to the person (and translated by the website)."""


def now() -> float:
    return road._now()


@dataclass
class Player:
    profile: str
    pub: str
    nickname: str
    avatar: str
    lang: str
    payload: dict | None = None
    run: object = None
    finished: bool = False
    forfeited: bool = False
    finished_at: float = 0.0
    last_seen: float = 0.0
    xp: int = 0
    badges: list = field(default_factory=list)


@dataclass
class Duel:
    code: str
    host: str
    lang: str
    seed: str
    pool: list
    players: list = field(default_factory=list)
    invited: list = field(default_factory=list)
    state: str = "lobby"       # lobby | countdown | racing | done | closed
    start_at: float = 0.0
    created: float = field(default_factory=now)
    result: dict | None = None


_duels: "OrderedDict[str, Duel]" = OrderedDict()


def reset() -> None:
    _duels.clear()


def _player(d: Duel, profile: str) -> Player | None:
    return next((p for p in d.players if p.profile == profile), None)


def _get(code: str, allow_closed: bool = False) -> Duel:
    d = _duels.get((code or "").strip().upper())
    if d is None:
        raise DuelError("That race isn't open any more.")
    _tick(d)
    if d.state == "closed" and not allow_closed:
        raise DuelError("That race isn't open any more.")
    return d


def view_by_code(code: str, profile: str, with_run: bool = False, lang: str = "en") -> dict:
    """The race as this driver sees it, by its code. A closed lobby is still shown (as closed) to the people who were waiting in it."""
    return view(_get(code, allow_closed=True), profile, with_run, lang)


def _card(profile: str) -> dict:
    a = accounts.get(profile)
    if a is None:
        raise DuelError("Make a profile first to race.")
    return a


def _join_player(d: Duel, profile: str, lang: str) -> Player:
    a = _card(profile)
    p = Player(profile, a["pub"], a["nickname"], a["avatar"], lang, last_seen=now())
    d.players.append(p)
    return p


def create(host: str, lang: str, invite_pubs: list[str] | None = None) -> Duel:
    """Open a lobby with this person in it, and (optionally) their friends asked in. The messages come from the host's language."""
    _card(host)
    for d in list(_duels.values()):
        _tick(d)
    if sum(1 for d in _duels.values() if d.host == host and d.state in ("lobby", "countdown", "racing")) >= MAX_OPEN:
        raise DuelError("You already have three races open. Finish or leave one first.")
    pool = sorted((i for i in gp.build_pool(lang) if i.source not in road.PRIVATE), key=lambda i: i.id)   # (nothing private: everyone races on the same messages)
    if sum(i.truth == "scam" for i in pool) < 5 or sum(i.truth == "safe" for i in pool) < 2:
        raise DuelError("Not enough messages for a race yet.")
    while True:
        code = "".join(secrets.choice(ALPHABET) for _ in range(6))
        if code not in _duels:
            break
    friends = {f["pub"] for f in accounts.friends(host)}
    d = Duel(code, host, lang, secrets.token_hex(8), pool, invited=[p for p in dict.fromkeys(invite_pubs or []) if p in friends])
    _join_player(d, host, lang)
    while len(_duels) >= 100:
        _duels.popitem(last=False)
    _duels[code] = d
    return d


def join(code: str, profile: str, lang: str) -> Duel:
    d = _get(code)
    if _player(d, profile):
        return d
    if d.state != "lobby":
        raise DuelError("That race has already started.")
    if len(d.players) >= MAX_PLAYERS:
        raise DuelError("That race is full.")
    _join_player(d, profile, lang)
    return d


def leave(code: str, profile: str) -> None:
    d = _duels.get((code or "").strip().upper())
    p = d and _player(d, profile)
    if d is None or p is None:
        return
    if d.state == "lobby":
        if d.host == profile:
            d.state = "closed"          # the host closes it: nobody is left waiting for a race that will not start
        else:
            d.players.remove(p)
    elif d.state in ("countdown", "racing") and not p.finished:
        p.finished, p.forfeited, p.finished_at = True, True, now()
        _tick(d)


def start(code: str, host: str) -> Duel:
    d = _get(code)
    if d.host != host:
        raise DuelError("Only the person who opened the race can start it.")
    if d.state != "lobby":
        raise DuelError("That race has already started.")
    if len(d.players) < 2:
        raise DuelError("Wait for at least one more driver.")
    d.start_at = now() + COUNTDOWN
    for p in d.players:  # every driver gets the same gates, from the same seed, timed from the same moment
        with db.as_profile(p.profile):
            p.payload = road.start(p.profile, p.lang, pool=d.pool, mode="duel", seed=d.seed, limit=GATES, duel=d.code, t0=d.start_at)
        p.run = road.get(p.payload["run"], p.profile)
        p.last_seen = now()
    d.state = "countdown"
    return d


def note_answer(run) -> None:
    """A driver passed a gate: their standing changes at once, and a driver whose drive is over is finished."""
    d = _duels.get(run.duel)
    p = d and _player(d, run.owner)
    if d is None or p is None:
        return
    p.last_seen = now()
    if run.over and not p.finished:
        p.finished, p.finished_at = True, now()
    _tick(d)


def heard_from(d: Duel, profile: str) -> None:
    p = _player(d, profile)
    if p:
        p.last_seen = now()


# ---------------------------------------------------------------- the race clock
def _tick(d: Duel) -> None:
    t = now()
    if d.state == "lobby" and t - d.created > LOBBY_TTL:
        d.state = "closed"
    if d.state == "countdown" and t >= d.start_at:
        d.state = "racing"
        for p in d.players:
            p.last_seen = t
    if d.state == "racing":
        over_time = t - d.start_at > RACE_MAX
        for p in d.players:
            if not p.finished and (over_time or t - p.last_seen > FORFEIT_AFTER):
                p.finished, p.forfeited, p.finished_at = True, True, t
        if all(p.finished for p in d.players):
            _settle(d)


def _standing(p: Player) -> dict:
    r = p.run
    return {"correct": r.correct if r else 0, "wrong": r.wrong if r else 0, "lives": r.lives if r else 0, "distance": r.distance if r else 0, "n": len(r.answered) if r else 0}


def _settle(d: Duel) -> None:
    """The race is over: rank the drivers, give out the XP and badges, record who beat whom."""
    if d.state == "done":
        return
    order = sorted(d.players, key=lambda p: (p.forfeited, -_standing(p)["correct"], -_standing(p)["lives"], p.finished_at))
    ranking = []
    for rank, p in enumerate(order, 1):
        st = _standing(p)
        ranking.append({"rank": rank, "pub": p.pub, "nickname": p.nickname, "avatar": p.avatar, **st, "time": round(max(0.0, p.finished_at - d.start_at), 1), "forfeit": p.forfeited})
    winner = order[0] if order and not order[0].forfeited else None
    for p in d.players:
        if p.forfeited:
            continue
        won = p is winner
        with db.as_profile(p.profile):
            s = gs.get()
            gain = XP_PLAY + (XP_WIN if won else 0)
            s["xp"] += gain
            s["duels_played"] += 1
            s["duel_wins"] += int(won)
            want = (["duel-win"] if s["duel_wins"] >= 1 else []) + (["duel-5"] if s["duel_wins"] >= 5 else [])
            new = [b for b in want if b not in s["badges"] and b in gs.BADGES]
            s["badges"] += new
            gs.save(s)
        p.xp, p.badges = gain, new
    pairs = []
    if winner is not None:
        for a in order:
            for b in order:
                if a is not b and order.index(a) < order.index(b) and not (a.forfeited and b.forfeited):
                    pairs.append((a.profile, b.profile))
    if pairs:
        ts = db.iso(db.now())
        with db.connect(shared=True) as c:
            for won, lost in pairs:
                x, y = sorted((won, lost))
                c.execute("INSERT INTO duel_pairs(a,b,winner,ts) VALUES(?,?,?,?)", (x, y, won, ts))
    d.result = {"ranking": ranking, "winner": winner.pub if winner else ""}
    d.state = "done"


# ---------------------------------------------------------------- what a browser sees
def record(me: str, other: str) -> list[int]:
    """[wins, losses] for `me` against `other` in live races."""
    a, b = sorted((me, other))
    with db.connect(shared=True) as c:
        rows = c.execute("SELECT winner FROM duel_pairs WHERE a=? AND b=?", (a, b)).fetchall()
    wins = sum(1 for r in rows if r["winner"] == me)
    return [wins, len(rows) - wins]


def view(d: Duel, profile: str, with_run: bool = False, lang: str = "en") -> dict:
    """The race as one driver may see it. Never a profile id, never an answer; the rivals' progress is which gates were right, careful or wrong, and when."""
    _tick(d)
    me = _player(d, profile)
    if me is None:
        raise DuelError("You are not in that race.")
    heard_from(d, profile)
    players = []
    for p in d.players:
        r = p.run
        prog = None
        if r is not None and d.state != "lobby":
            prog = {"n": len(r.answered), "path": "".join(r.path), "times": list(r.times), "correct": r.correct, "lives": r.lives, "distance": r.distance, "finished": p.finished, "forfeited": p.forfeited}
        skin = {}
        if r is not None:
            from core.game import garage

            with db.as_profile(p.profile):
                sel = garage.selected(p.profile)
            skin = {"car": sel["car"], "hat": sel["hat"]}
        players.append({"pub": p.pub, "nickname": p.nickname, "avatar": p.avatar, "you": p.profile == profile, "host": p.profile == d.host, "progress": prog, **skin,
                        "record": record(profile, p.profile) if p.profile != profile else None})
    out = {"code": d.code, "state": d.state, "now": now(), "start_at": d.start_at, "gates": GATES, "players": players, "can_start": d.state == "lobby" and d.host == profile and len(d.players) >= 2,
           "you_host": d.host == profile, "full": len(d.players) >= MAX_PLAYERS, "result": None}
    if with_run and me.payload is not None and d.state != "lobby":
        out["you_run"] = me.payload
    if d.result is not None:
        mine = next((x for x in d.result["ranking"] if x["pub"] == me.pub), None)
        out["result"] = {**d.result, "you": {"rank": mine["rank"] if mine else 0, "won": d.result["winner"] == me.pub, "xp": me.xp, "badges": [{"id": b, "title": gs.badge_text(b, lang)[0], "desc": gs.badge_text(b, lang)[1]} for b in me.badges]}}
    return out


def invites_for(profile: str) -> list[dict]:
    """Open lobbies this person has been asked into and has not joined yet: [{code, host nickname, avatar, players}]."""
    a = accounts.get(profile)
    if a is None:
        return []
    out = []
    for d in list(_duels.values()):
        _tick(d)
        if d.state == "lobby" and a["pub"] in d.invited and _player(d, profile) is None and len(d.players) < MAX_PLAYERS:
            h = d.players[0]
            out.append({"code": d.code, "host": h.nickname, "avatar": h.avatar, "players": len(d.players)})
    return out


def mine(profile: str) -> list[dict]:
    """The races this person is in that are not over: [{code, state, players}]."""
    out = []
    for d in list(_duels.values()):
        _tick(d)
        if d.state in ("lobby", "countdown", "racing") and _player(d, profile):
            out.append({"code": d.code, "state": d.state, "players": len(d.players), "host": d.host == profile})
    return out


def invited_profiles(d: Duel, host: str) -> list[str]:
    """INTERNAL: the profile ids of the friends asked into this race (to notify them). Never for a browser."""
    wanted = set(d.invited)
    with db.connect(shared=True) as c:
        rows = c.execute("SELECT a2.profile, a2.pub FROM friendships f JOIN accounts a2 ON a2.profile=f.b WHERE f.a=?", (host,)).fetchall()
    return [r["profile"] for r in rows if r["pub"] in wanted]

