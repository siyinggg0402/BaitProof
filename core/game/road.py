"""Scam Road: an endless drive. Each gate shows a message and three lanes (left: scam, middle: check first, right: looks fine); the lane you drive
through is your answer, graded HERE, so the browser never sees an answer before it gives one. A right lane adds a stretch of road, a wrong lane
costs a heart, and the run ends at no hearts. The distance is computed from graded answers only, so nobody can post a made-up score. It feeds the
same personal trick model and XP as every other game, and finished runs go on the friends' leaderboard.

Two ways to drive: the free drive (a fresh mix every time) and the Daily Road (the same messages, in the same order, for everyone who reads the same
language that day: it is how friends race each other's ghosts)."""
from __future__ import annotations

import math
import random
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field

from core.domain.tactics import TACTICS
from core.game import engine, garage
from core.game import pool as gp
from core.game import state as gs
from core.lang.i18n import norm, tactic_text
from core.storage import accounts, model, runs

GATE = 80  # metres of road earned by each right answer
LIVES = 3
LANES = ("scam", "unsure", "safe")  # left, middle, right
AHEAD = 5  # messages the browser holds ahead of the car
SPEED = {"base": 14.0, "step": 0.4, "max": 26.0}  # metres per second at gate 0, added per gate, and the top speed: the browser drives, the server only scores
XP_FAR = 10  # for a drive of at least 400 m
XP_DAILY_ROAD = 30  # the first Daily Road of the day
TTL = 3600.0
MIX = (0.4, 0.2)  # per scam in a bag: this many genuine messages and this many "check first" ones
MODES = ("road", "daily", "duel")
PRIVATE = ("yours", "family")  # messages from a person's own circle: never in the Daily Road, which must be the same for everyone


class RoadError(ValueError):
    pass


def _now() -> float:
    """The clock (seconds since 1970): one place to change in a test, and the one clock a live race and its drivers share."""
    return time.time()


@dataclass
class Run:
    id: str
    owner: str
    lang: str
    mode: str = "road"
    day: str = ""
    gates: list[tuple[str, gp.Item]] = field(default_factory=list)  # every gate dealt so far, in order: ("g0", message). A message can come round again, a gate never does
    bag: list[gp.Item] = field(default_factory=list)
    answered: dict = field(default_factory=dict)
    path: list[str] = field(default_factory=list)  # one letter per answered gate: c right, p careful, w wrong
    lives: int = LIVES
    distance: int = 0
    combo: int = 0
    best_combo: int = 0
    correct: int = 0
    partial: int = 0
    wrong: int = 0
    xp: int = 0
    start_level: int = 1
    finished: bool = False
    summary: dict | None = None
    created: float = field(default_factory=time.time)
    pool: list[gp.Item] = field(default_factory=list)
    rng: random.Random = field(default_factory=random.Random)
    limit: int = 0         # a live race has a fixed number of gates (0: endless)
    duel: str = ""         # the live race this drive belongs to, if any
    t0: float = 0.0        # when the race started (the clock every answer's time is measured from)
    times: list[float] = field(default_factory=list)  # seconds after the start at which each gate was answered

    @property
    def over(self) -> bool:
        return self.lives <= 0 or bool(self.limit and len(self.answered) >= self.limit)

    @property
    def game(self) -> str:
        return runs.DUEL if self.mode == "duel" else runs.DAILY if self.mode == "daily" else runs.ROAD


_runs: "OrderedDict[str, Run]" = OrderedDict()


def _store(r: Run) -> None:
    now = time.time()
    for k in [k for k, v in _runs.items() if now - v.created > TTL]:
        _runs.pop(k, None)
    while len(_runs) >= 300:
        _runs.popitem(last=False)
    _runs[r.id] = r


def get(run_id: str, owner: str) -> Run:
    r = _runs.get(run_id)
    if r is None or time.time() - r.created > TTL or r.owner != owner:
        raise RoadError("That drive has expired. Start a new one.")
    return r


def _fill_bag(r: Run) -> None:
    scams = [i for i in r.pool if i.truth == "scam"]
    safes = [i for i in r.pool if i.truth == "safe"]
    unsure = [i for i in r.pool if i.truth == "unsure"]
    bag = scams + r.rng.sample(safes, min(len(safes), math.ceil(len(scams) * MIX[0]))) + r.rng.sample(unsure, min(len(unsure), math.ceil(len(scams) * MIX[1])))
    r.rng.shuffle(bag)
    recent = {i.id for _, i in r.gates[-4:]}
    bag.sort(key=lambda i: i.id in recent)  # (stable) the ones just shown go to the back, so a refill never repeats the last message at once
    r.bag = bag


def _deal(r: Run, n: int) -> list[tuple[str, gp.Item]]:
    out = []
    for _ in range(n):
        if not r.bag:
            _fill_bag(r)
        gate = (f"g{len(r.gates)}", r.bag.pop(0))
        r.gates.append(gate)
        out.append(gate)
    return out


def _public(gates: list[tuple[str, gp.Item]]) -> list[dict]:
    return [{"id": gid, "text": i.text, "yours": i.source == "yours", "family": i.source == "family"} for gid, i in gates]


def _skin(owner: str) -> dict:
    sel = garage.selected(owner)
    return {**sel, "color": garage.CARS[sel["car"]][0]}


def start(owner: str, lang: str = "en", pool: list[gp.Item] | None = None, mode: str = "road", seed: str = "", limit: int = 0, duel: str = "", t0: float = 0.0) -> dict:
    if mode not in MODES:
        raise RoadError("Pick a drive.")
    lang = norm(lang)
    pool = pool if pool is not None else gp.build_pool(lang)
    daily = mode == "daily"
    if mode == "duel":  # a live race: the pool and the seed are fixed by the race, so every driver gets the very same gates
        pass
    elif daily:  # the same bag for everyone: no private messages, a fixed order, and a shuffle seeded by the day and the language
        pool = sorted((i for i in pool if i.source not in PRIVATE), key=lambda i: i.id)
    if sum(i.truth == "scam" for i in pool) < 5 or sum(i.truth == "safe" for i in pool) < 2:
        raise RoadError("Not enough messages for a drive yet.")
    day = gs.today()
    rng = random.Random(seed) if seed else random.Random(f"road|{day}|{lang}") if daily else random.Random(random.getrandbits(64))
    r = Run(uuid.uuid4().hex[:12], owner, lang, mode=mode, day=day if daily else "", pool=pool, rng=rng, start_level=gs.level_for(gs.get()["xp"]), limit=limit, duel=duel, t0=t0)
    first = _deal(r, min(AHEAD + 1, limit) if limit else AHEAD + 1)
    _store(r)
    live = mode == "duel"
    return {"run": r.id, "mode": mode, "day": r.day, "lives": r.lives, "gate": GATE, "speed": SPEED, "lanes": list(LANES), "items": _public(first), "limit": limit,
            "ghosts": [] if daily or live else runs.ghosts(owner), "replays": runs.replays(owner, runs.DAILY) if daily else [],
            "best": 0 if live else runs.best(owner, r.game, runs.day_start() if daily else ""), "account": accounts.get(owner) is not None, "skin": _skin(owner)}


def _grade(item: gp.Item, lane: int) -> str:
    choice = LANES[lane]
    if choice == item.truth:
        return "correct"
    return "partial" if choice == "unsure" else "wrong"  # being careful is never punished, but it takes you nowhere either


def answer(r: Run, gate_id: str, lane: int, lang: str = "en") -> dict:
    if r.finished or r.over:
        raise RoadError("This drive is over.")
    item = next((i for gid, i in r.gates if gid == gate_id), None)
    if item is None:
        raise RoadError("That message isn't part of this drive.")
    if gate_id in r.answered:
        raise RoadError("Already answered.")
    if lane not in (0, 1, 2):
        raise RoadError("Pick a lane.")
    outcome = _grade(item, lane)
    gain = 0
    if outcome == "correct":
        gain = engine.XP_CORRECT + engine.XP_COMBO_STEP * min(r.combo, engine.XP_COMBO_CAP)
        r.combo += 1
        r.best_combo = max(r.best_combo, r.combo)
        r.correct += 1
        r.distance += GATE
    elif outcome == "partial":
        gain, r.combo, r.partial = engine.XP_PARTIAL, 0, r.partial + 1
    else:
        r.combo, r.wrong, r.lives = 0, r.wrong + 1, r.lives - 1
    r.xp += gain
    r.answered[gate_id] = outcome
    r.path.append({"correct": "c", "partial": "p", "wrong": "w"}[outcome])
    r.times.append(round(max(0.0, _now() - r.t0), 2) if r.t0 else 0.0)
    if item.truth == "scam" and item.tactic:
        model.record_result(item.tactic, {"correct": "correct", "partial": "partial", "wrong": "incorrect"}[outcome])
    s = gs.get()
    s["xp"] += gain
    s["seen"] = ([item.id] + [x for x in s["seen"] if x != item.id])[:60]
    if outcome == "correct" and item.source in PRIVATE:
        s["yours_correct"] += 1
    gs.save(s)
    tell, action = engine._explain(item, lang)
    ahead = len(r.gates) - len(r.answered)
    want = max(0, AHEAD - ahead + 1)
    if r.limit:
        want = min(want, max(0, r.limit - len(r.gates)))
    more = [] if r.over else _deal(r, want)
    if r.duel:
        from core.game import duel as duels  # (a live race watches every answer: its standings update the moment a gate is passed)

        duels.note_answer(r)
    return {"outcome": outcome, "truth": item.truth, "lane": LANES.index(item.truth), "xp": gain, "combo": r.combo, "lives": r.lives, "distance": r.distance, "over": r.over,
            "tell": tell, "action": action, "tell_phrase": item.tell_phrase, "tricks": [tactic_text(t, "label", lang, TACTICS) for t in item.tactics if t in TACTICS],
            "next": _public(more), "yours": item.source == "yours", "family": item.source == "family"}


def finish(r: Run, lang: str = "en") -> dict:
    if r.summary is not None:
        return _speak(r, lang)
    if r.mode == "duel":
        return _finish_duel(r, lang)
    s = gs.get()
    progress_before = garage.progress(r.owner)
    daily = r.mode == "daily"
    scope = "day" if daily else "all"
    before = runs.best(r.owner, r.game, runs.since(scope))
    rivals = runs.friend_bests(r.owner, r.game, scope)      # (profile id, card): the ids stay on the server
    bonus = XP_FAR if r.distance >= 400 else 0
    first_daily = daily and bool(r.answered) and s["road_daily_last"] != r.day
    if first_daily:
        bonus += XP_DAILY_ROAD
        s["road_daily_last"], s["road_daily_count"] = r.day, s["road_daily_count"] + 1
    s["xp"] += bonus
    r.xp += bonus
    if r.answered:
        s["rounds"] += 1
        s["correct_total"] += r.correct
        gs.touch_streak(s)
        sel = garage.selected(r.owner)
        runs.record(r.owner, r.game, r.distance, r.correct, "".join(r.path), f"{sel['car']}:{sel['hat']}")
    s["best_combo"] = max(s["best_combo"], r.best_combo)
    passed = [(pid, g) for pid, g in rivals if before < g["best"] <= r.distance]
    want = ["first-round"] if r.answered else []
    if r.distance >= 500:
        want.append("road-500")
    if passed:
        want.append("road-ahead")
    if first_daily:
        want.append("road-daily")
    if s["best_combo"] >= 5:
        want.append("combo-5")
    if s["streak"] >= 3:
        want.append("streak-3")
    new = [b for b in dict.fromkeys(want) if b not in s["badges"] and b in gs.BADGES]
    s["badges"] += new
    level = gs.level_for(s["xp"])
    gs.save(s)
    r.finished = True
    unlocked = _unlocked_between(progress_before, garage.progress(r.owner))
    r.summary = {"mode": r.mode, "distance": r.distance, "correct": r.correct, "partial": r.partial, "wrong": r.wrong, "best_combo": r.best_combo, "xp_gained": r.xp, "level_up": level > r.start_level,
                 "level_before": r.start_level, "level": level, "new_best": bool(r.answered) and r.distance > before, "personal_best": max(before, r.distance),
                 "passed": [{"nickname": g["nickname"], "avatar": g["avatar"], "best": g["best"]} for _, g in passed], "badges_new": [{"id": b} for b in new],
                 "board": runs.board(r.owner, "day" if daily else "week", r.game)[:6] if accounts.get(r.owner) else [], "account": accounts.get(r.owner) is not None,
                 "unlocked": unlocked, "first_daily": first_daily}
    if passed and r.answered:
        from core.storage import push  # (a friend who asked is told that you passed them; best effort, never blocks the drive)

        push.notify_passed(r.owner, [(pid, g["best"]) for pid, g in passed], r.distance, r.game)
    return _speak(r, lang)


def _finish_duel(r: Run, lang: str) -> dict:
    """The end of a drive in a live race: the distance is recorded; the race itself (the winner, the XP, the badges) is settled by the duel module."""
    if r.summary is None:
        if r.answered:
            sel = garage.selected(r.owner)
            runs.record(r.owner, r.game, r.distance, r.correct, "".join(r.path), f"{sel['car']}:{sel['hat']}")
        r.finished = True
        r.summary = {"mode": "duel", "distance": r.distance, "correct": r.correct, "partial": r.partial, "wrong": r.wrong, "best_combo": r.best_combo, "xp_gained": r.xp, "level_up": False,
                     "new_best": False, "personal_best": r.distance, "passed": [], "badges_new": [], "board": [], "account": True, "unlocked": [], "first_daily": False}
    return _speak(r, lang)


def _unlocked_between(before: dict, after: dict) -> list[dict]:
    """Cars and hats that this drive unlocked: met now, not met by the progress the player had before it."""
    out = [{"kind": "car", "id": i} for i, (_, need) in garage.CARS.items() if garage.met(need, after) and not garage.met(need, before)]
    return out + [{"kind": "hat", "id": i} for i, need in garage.HATS.items() if garage.met(need, after) and not garage.met(need, before)]


def _speak(r: Run, lang: str) -> dict:
    out = dict(r.summary)
    out["badges_new"] = [{"id": b["id"], "title": gs.badge_text(b["id"], lang)[0], "desc": gs.badge_text(b["id"], lang)[1]} for b in r.summary["badges_new"]]
    names = {**{("car", i): n for i, n in garage.CAR_NAMES.items()}, **{("hat", i): n for i, n in garage.HAT_NAMES.items()}}
    from core.lang.i18n import tr

    out["unlocked"] = [{**u, "name": tr(names[(u["kind"], u["id"])], lang)} for u in r.summary["unlocked"]]
    return out
