"""Game runs for the friends' leaderboard and for ghosts: a score per finished run (the server computes it from graded answers; the browser cannot
claim one), the outcome of every gate ("c" right, "p" careful, "w" wrong: enough to replay the pace of a drive, never what the answers were), and the
car the driver had. Only friends see each other's rows. Lives in the SHARED database."""
from __future__ import annotations

from datetime import timedelta

from core.storage import db

ROAD = "road"      # the endless drive
DAILY = "daily"    # the Daily Road: the same messages for everyone today
LINK = "link"      # Link Hunt
DUEL = "duel"      # a live race (its distance, for the record; its winners are in duel_pairs)


def day_start() -> str:
    """Midnight UTC today, as the same ISO text the runs are stamped with."""
    return db.iso(db.now().replace(hour=0, minute=0, second=0, microsecond=0))


def week_start() -> str:
    """Monday 00:00 UTC of this week."""
    today = db.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return db.iso(today - timedelta(days=today.weekday()))


def since(scope: str) -> str:
    return day_start() if scope == "day" else week_start() if scope == "week" else ""


def record(profile: str, game: str, score: int, correct: int = 0, path: str = "", skin: str = "") -> None:
    with db.connect(shared=True) as c:
        c.execute("INSERT INTO runs(profile,game,score,correct,ts,path,skin) VALUES(?,?,?,?,?,?,?)", (profile, game, int(score), int(correct), db.iso(db.now()), path[:400], skin[:40]))


def best(profile: str, game: str = ROAD, since: str = "") -> int:
    with db.connect(shared=True) as c:
        r = c.execute("SELECT COALESCE(MAX(score),0) AS m FROM runs WHERE profile=? AND game=? AND ts>=?", (profile, game, since)).fetchone()
    return r["m"]


def best_distance(profile: str) -> int:
    """The farthest this profile has driven on either road (what unlocks cars and hats)."""
    return max(best(profile, ROAD), best(profile, DAILY))


def board(me: str, scope: str = "week", game: str = ROAD) -> list[dict]:
    """You and your friends, best first: [{rank, pub, nickname, avatar, best, runs, you}] (never a profile id: those are session cookies).
    Friends with no run in this scope come last, unranked."""
    start = since(scope)
    with db.connect(shared=True) as c:
        people = c.execute("SELECT a.profile, a.pub, a.nickname, a.avatar FROM accounts a WHERE a.profile=? OR a.profile IN (SELECT b FROM friendships WHERE a=?)", (me, me)).fetchall()
        stats = {r["profile"]: r for r in c.execute(
            "SELECT profile, MAX(score) AS best, COUNT(*) AS n FROM runs WHERE game=? AND ts>=? GROUP BY profile", (game, start)).fetchall()}
    return _rank(me, people, stats)


def _rank(me: str, people, stats) -> list[dict]:
    rows = []
    for p in people:
        s = stats.get(p["profile"])
        rows.append({"pub": p["pub"], "nickname": p["nickname"], "avatar": p["avatar"], "best": s["best"] if s else 0, "runs": s["n"] if s else 0, "you": p["profile"] == me})
    rows.sort(key=lambda r: (r["runs"] == 0, -r["best"], not r["you"], r["nickname"].lower()))
    rank = 0
    for r in rows:
        if r["runs"]:
            rank += 1
        r["rank"] = rank if r["runs"] else 0
    return rows


def group_board(me: str, members: list[str], scope: str = "week", game: str = ROAD) -> list[dict]:
    """The same ranking among the members of a family group (profile ids of the members, which the caller got from the group tables)."""
    start = since(scope)
    if not members:
        return []
    marks = ",".join("?" * len(members))
    with db.connect(shared=True) as c:
        people = c.execute(f"SELECT profile, pub, nickname, avatar FROM accounts WHERE profile IN ({marks})", members).fetchall()
        stats = {r["profile"]: r for r in c.execute(
            f"SELECT profile, MAX(score) AS best, COUNT(*) AS n FROM runs WHERE game=? AND ts>=? AND profile IN ({marks}) GROUP BY profile", (game, start, *members)).fetchall()}
    return _rank(me, people, stats)


def ghosts(me: str, game: str = ROAD) -> list[dict]:
    """Your friends' all-time best distances, nearest first, for the flags beside the road: [{nickname, avatar, best}]."""
    rows = [r for r in board(me, "all", game) if not r["you"] and r["best"] > 0]
    return sorted(({"nickname": r["nickname"], "avatar": r["avatar"], "best": r["best"]} for r in rows), key=lambda r: r["best"])


def friend_bests(me: str, game: str = ROAD, scope: str = "all") -> list[tuple[str, dict]]:
    """INTERNAL: each friend's best in this scope as (profile id, {nickname, avatar, best}). The profile id is a session cookie: it is for the server's own
    use (to notify a friend, say) and must never be put in anything a browser receives."""
    start = since(scope)
    with db.connect(shared=True) as c:
        rows = c.execute(
            "SELECT a.profile, a.nickname, a.avatar, COALESCE(MAX(r.score),0) AS best FROM friendships f JOIN accounts a ON a.profile=f.b "
            "LEFT JOIN runs r ON r.profile=a.profile AND r.game=? AND r.ts>=? WHERE f.a=? GROUP BY a.profile", (game, start, me)).fetchall()
    return [(r["profile"], {"nickname": r["nickname"], "avatar": r["avatar"], "best": r["best"]}) for r in rows if r["best"] > 0]


def replays(me: str, game: str = DAILY, scope: str = "day") -> list[dict]:
    """The best drive today of you and each friend, as a path to race against: [{pub, nickname, avatar, score, path, car, hat, you}].
    A path says only whether each gate was right, careful or wrong, so it can show how a friend drove without giving a single answer away."""
    start = since(scope)
    with db.connect(shared=True) as c:
        people = c.execute("SELECT a.profile, a.pub, a.nickname, a.avatar FROM accounts a WHERE a.profile=? OR a.profile IN (SELECT b FROM friendships WHERE a=?)", (me, me)).fetchall()
        out = []
        for p in people:
            r = c.execute("SELECT score, path, skin FROM runs WHERE profile=? AND game=? AND ts>=? AND path<>'' ORDER BY score DESC, id DESC LIMIT 1", (p["profile"], game, start)).fetchone()
            if r:
                car, _, hat = (r["skin"] or "").partition(":")
                out.append({"pub": p["pub"], "nickname": p["nickname"], "avatar": p["avatar"], "score": r["score"], "path": r["path"], "car": car, "hat": hat, "you": p["profile"] == me})
    return sorted(out, key=lambda r: -r["score"])
