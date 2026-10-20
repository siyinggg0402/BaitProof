"""Game rounds: pick the messages, score the answers, track lives and combos, award XP and badges, and feed every result into the same
personal trick model the Practice page uses (so playing improves your resilience map). Answers never leave the server until revealed."""
from __future__ import annotations

import random
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field

from core.lang.i18n import norm, tactic_text
from core.domain.tactics import TACTICS
from core.game import pool as gp
from core.game import state as gs
from core.storage import model

MODES = ("rush", "daily", "tell", "boss", "yours")
LIVES = 3
XP_CORRECT, XP_PARTIAL, XP_TELL, XP_COMBO_STEP, XP_COMBO_CAP, XP_FAST = 10, 5, 15, 2, 5, 5
XP_FINISH, XP_PERFECT, XP_DAILY, XP_BOSS = 10, 20, 50, 40
CHOICES = ("scam", "safe", "unsure")
TTL = 3600.0


class GameError(ValueError):
    pass


@dataclass
class Round:
    id: str
    mode: str
    items: list[gp.Item]
    trick: str = ""
    lives: int = 0
    combo: int = 0
    best_combo: int = 0
    correct: int = 0
    partial: int = 0
    wrong: int = 0
    xp: int = 0
    answered: dict = field(default_factory=dict)
    start_level: int = 1
    finished: bool = False
    summary: dict | None = None
    created: float = field(default_factory=time.time)
    daily_key: str = ""
    owner: str = ""  # the profile that started it: nobody else may answer it

    @property
    def over(self) -> bool:
        return len(self.answered) >= len(self.items) or (self.mode == "boss" and self.lives <= 0)


_rounds: "OrderedDict[str, Round]" = OrderedDict()


def _store(r: Round) -> None:
    now = time.time()
    for k in [k for k, v in _rounds.items() if now - v.created > TTL]:
        _rounds.pop(k, None)
    while len(_rounds) >= 300:
        _rounds.popitem(last=False)
    _rounds[r.id] = r


def get(round_id: str, owner: str = "") -> Round:
    r = _rounds.get(round_id)
    if r is None or time.time() - r.created > TTL or r.owner != owner:
        raise GameError("That round has expired. Start a new one.")
    return r


# ---------------------------------------------------------------- choosing the messages
def _weak_tricks(n: int = 4) -> list[str]:
    from core.pipelines import train

    return [t for t, _ in train.select_tactics(n)]


def _pick(candidates: list[gp.Item], n: int, rnd: random.Random, seen: set[str]) -> list[gp.Item]:
    """Prefer messages not seen recently, then fill from the rest. Never repeats within a pick."""
    fresh = [i for i in candidates if i.id not in seen]
    rnd.shuffle(fresh)
    rest = [i for i in candidates if i.id in seen]
    rnd.shuffle(rest)
    return (fresh + rest)[:n]


def select(mode: str, trick: str, rnd: random.Random, state: dict, items: list[gp.Item]) -> list[gp.Item]:
    seen = set(state["seen"])
    scams = [i for i in items if i.truth == "scam"]
    safes = [i for i in items if i.truth == "safe"]
    unsure = [i for i in items if i.truth == "unsure"]
    if mode == "boss":
        if trick not in TACTICS:
            raise GameError("Pick one of the tricks to challenge.")
        mine = [i for i in scams if trick in i.tactics]
        chosen = _pick(mine, 6, rnd, seen)
        chosen += _pick(safes, 2, rnd, seen)
    elif mode == "tell":
        chosen = _pick([i for i in scams if len(i.tell_phrase.split()) >= 2 or (gp.is_cjk(i.text) and i.tell_phrase)], 5, rnd, seen)  # Chinese phrases have no spaces
    elif mode == "yours":
        chosen = _pick([i for i in scams if i.source == "yours"], 5, rnd, seen)
        if not chosen:
            raise GameError("No scams from your own circle yet. Check a message first and it will appear here.")
    elif mode == "daily":
        chosen = _pick(scams, 4, rnd, set()) + _pick(safes, 1, rnd, set()) + _pick(unsure, 1, rnd, set())
    else:  # rush: weighted towards the tricks this person is weakest at, plus their own family's scams
        weak = set(_weak_tricks())
        yours = [i for i in scams if i.source == "yours"]
        targeted = [i for i in scams if set(i.tactics) & weak and i.source != "yours"]
        chosen = _pick(yours, 2, rnd, seen)
        chosen += _pick([i for i in targeted if i not in chosen], 5 - len(chosen), rnd, seen)
        chosen += _pick([i for i in scams if i not in chosen], 5 - len(chosen), rnd, seen)
        chosen += _pick(safes, 2, rnd, seen) + _pick(unsure, 1, rnd, seen)
    rnd.shuffle(chosen)
    return chosen


def start(mode: str, trick: str = "", items: list[gp.Item] | None = None, owner: str = "", lang: str = "en") -> Round:
    if mode not in MODES:
        raise GameError("Unknown game mode.")
    state = gs.get()
    rnd = random.Random(f"daily-{gs.today()}") if mode == "daily" else random.Random()
    if items is None:
        items = gp.build_pool(lang)  # the messages are in the player's language
    pool_items = sorted(items, key=lambda i: i.id) if mode == "daily" else items
    chosen = select(mode, trick, rnd, state, pool_items)
    if len(chosen) < 3:
        raise GameError("Not enough messages for that mode yet.")
    r = Round(uuid.uuid4().hex[:12], mode, chosen, trick=trick if mode == "boss" else "", lives=LIVES if mode == "boss" else 0,
              start_level=gs.level_for(state["xp"]), daily_key=gs.today() if mode == "daily" else "", owner=owner)
    _store(r)
    return r


def public(r: Round, lang: str = "en") -> dict:
    """What the browser sees: the messages, never the answers."""
    out = []
    for i in r.items:
        d = {"id": i.id, "text": i.text, "yours": i.source == "yours"}
        if r.mode == "tell":
            d["words"] = gp.words(i.text)
        out.append(d)
    return {"round": r.id, "mode": r.mode, "trick": r.trick, "trick_label": tactic_text(r.trick, "label", lang, TACTICS) if r.trick else "", "lives": r.lives, "total": len(r.items), "items": out}


# ---------------------------------------------------------------- scoring an answer
def _tell_score(item: gp.Item, picked: list[int]) -> str:
    if gp.is_cjk(item.text):  # Chinese: the tappable units are clauses, scored by overlap with the giveaway's span
        return gp.tell_score_clauses(item, picked)
    toks = {gp.norm_word(w) for w in item.tell_phrase.split()} - {""}
    ws = gp.words(item.text)
    sel = {gp.norm_word(ws[i]) for i in picked if 0 <= i < len(ws)} - {""}
    if not toks or not sel:
        return "wrong"
    hit = len(toks & sel)
    recall, precision = hit / len(toks), hit / len(sel)
    grabbed_most = len({i for i in picked if 0 <= i < len(ws)}) > 0.7 * len(ws)  # selecting nearly everything is not finding the tell
    return "correct" if recall >= 0.6 and precision >= 0.5 and not grabbed_most else ("partial" if hit else "wrong")


def _grade(r: Round, item: gp.Item, choice: str | None, picked: list[int] | None) -> str:
    if r.mode == "tell":
        return _tell_score(item, picked or [])
    if choice not in CHOICES:
        raise GameError("Choose scam, looks fine, or check first.")
    if choice == item.truth:
        return "correct"
    if choice == "unsure":  # being careful is never punished: it earns partial credit
        return "partial"
    return "wrong"


def answer(r: Round, item_id: str, choice: str | None = None, picked: list[int] | None = None, fast: bool = False, lang: str = "en") -> dict:
    if r.finished:
        raise GameError("This round is already finished.")
    item = next((i for i in r.items if i.id == item_id), None)
    if item is None:
        raise GameError("That message isn't part of this round.")
    if item_id in r.answered:
        raise GameError("Already answered.")
    if r.mode == "boss" and r.lives <= 0:
        raise GameError("No lives left. Start the battle again.")
    outcome = _grade(r, item, choice, picked)
    gain = 0
    if outcome == "correct":
        gain = (XP_TELL if r.mode == "tell" else XP_CORRECT) + XP_COMBO_STEP * min(r.combo, XP_COMBO_CAP) + (XP_FAST if fast else 0)
        r.combo += 1
        r.best_combo = max(r.best_combo, r.combo)
        r.correct += 1
    elif outcome == "partial":
        gain, r.partial = XP_PARTIAL, r.partial + 1
    else:
        r.combo, r.wrong = 0, r.wrong + 1
        if r.mode == "boss":
            r.lives -= 1
    r.xp += gain
    r.answered[item_id] = outcome
    # the same personal model that Practice uses: only scams carry a trick to learn
    if item.truth == "scam" and item.tactic and r.mode != "tell":
        model.record_result(item.tactic, {"correct": "correct", "partial": "partial", "wrong": "incorrect"}[outcome])
    s = gs.get()
    s["xp"] += gain
    s["seen"] = ([item_id] + [x for x in s["seen"] if x != item_id])[:60]
    if outcome == "correct" and item.source == "yours":
        s["yours_correct"] += 1
    if outcome == "correct" and r.mode == "tell":
        s["tells_found"] += 1
    gs.save(s)
    span = gp.phrase_span(item.text, item.tell_phrase)
    careful = item.truth == "safe" and choice == "scam"
    tell, action = _explain(item, lang)
    return {
        "outcome": outcome, "truth": item.truth, "xp": gain, "combo": r.combo, "lives": r.lives, "over": r.over, "answered": len(r.answered), "total": len(r.items),
        "tell": tell, "action": action, "highlight": list(span) if span else None, "tell_phrase": item.tell_phrase,
        "tricks": [tactic_text(t, "label", lang, TACTICS) for t in item.tactics if t in TACTICS], "false_alarm": careful, "yours": item.source == "yours",
        "level": gs.level_for(s["xp"]),
    }


def _explain(item: gp.Item, lang: str) -> tuple[str, str]:
    """The explanation and the safe next step, in the reader's language. English is the item's own text. A Chinese reader gets the item's own
    Chinese text (in the right script); for a message that only has an English explanation (one the person forwarded earlier, say) the
    trick's own plain-language explanation stands in, so the page is never half English."""
    from core.pipelines.train import localized

    return localized(item.tell, item.tactic, "tell", lang, safe=item.truth != "scam"), localized(item.action, item.tactic, "action", lang, safe=item.truth != "scam")


# ---------------------------------------------------------------- finishing
def finish(r: Round, lang: str = "en") -> dict:
    if r.summary is not None:
        return _speak(r, lang)
    s = gs.get()
    done = len(r.answered) >= len(r.items) or r.over
    bonus = 0
    perfect = done and r.wrong == 0 and r.partial == 0 and len(r.answered) >= len(r.items)
    if done:
        bonus += XP_FINISH
    if perfect:
        bonus += XP_PERFECT
    daily_first = r.mode == "daily" and done and s["daily_done"] != gs.today()
    if daily_first:
        bonus += XP_DAILY
        s["daily_done"] = gs.today()
    won_boss = r.mode == "boss" and done and r.lives > 0
    if won_boss:
        bonus += XP_BOSS
        if r.trick not in s["boss_won"]:
            s["boss_won"].append(r.trick)
    s["xp"] += bonus
    r.xp += bonus
    if done:
        s["rounds"] += 1
        s["correct_total"] += r.correct
        gs.touch_streak(s)
    s["best_combo"] = max(s["best_combo"], r.best_combo)
    earned = _award(s, r, done, perfect, daily_first, won_boss)
    level = gs.level_for(s["xp"])
    gs.save(s)
    r.finished = True
    r.summary = {
        "mode": r.mode, "completed": done, "defeated": r.mode == "boss" and r.lives <= 0, "won_boss": won_boss, "trick_label": TACTICS[r.trick]["label"] if r.trick else "",
        "correct": r.correct, "partial": r.partial, "wrong": r.wrong, "total": len(r.items), "perfect": perfect, "best_combo": r.best_combo, "xp_gained": r.xp,
        "level_up": level > r.start_level, "level_before": r.start_level, "badges_new": earned, "daily_bonus": daily_first, "state": gs.summary(s),
        "resilience": model.baitproof_score(),
    }
    return _speak(r, lang)


def _speak(r: Round, lang: str) -> dict:
    """The finished round's summary with its names and titles in the reader's language (the stored copy stays in English)."""
    lang, summary = norm(lang), r.summary
    if lang == "en":
        return summary
    out = dict(summary)
    out["trick_label"] = tactic_text(r.trick, "label", lang, TACTICS) if r.trick else ""
    out["badges_new"] = [{"id": b["id"], "title": gs.badge_text(b["id"], lang)[0], "desc": gs.badge_text(b["id"], lang)[1]} for b in summary["badges_new"]]
    out["state"] = {**summary["state"], "title": gs.title_for(summary["state"]["level"], lang),
                    "badges": [{"id": b["id"], "title": gs.badge_text(b["id"], lang)[0], "desc": gs.badge_text(b["id"], lang)[1]} for b in summary["state"]["badges"]]}
    return out


def _award(s: dict, r: Round, done: bool, perfect: bool, daily_first: bool, won_boss: bool) -> list[dict]:
    want = []
    if done:
        want.append("first-round")
    if perfect:
        want.append("perfect-round")
    if s["best_combo"] >= 5:
        want.append("combo-5")
    if s["streak"] >= 3:
        want.append("streak-3")
    if s["streak"] >= 7:
        want.append("streak-7")
    if daily_first or s["daily_done"] == gs.today():
        want.append("daily-first")
    lvl = gs.level_for(s["xp"])
    want += [b for b, n in (("level-3", 3), ("level-5", 5)) if lvl >= n]
    if s["yours_correct"] >= 5:
        want.append("yours-5")
    if s["tells_found"] >= 5:
        want.append("tell-5")
    if won_boss:
        want.append(f"boss:{r.trick}")
    new = [b for b in dict.fromkeys(want) if b not in s["badges"] and b in gs.BADGES]
    s["badges"] += new
    return [{"id": b, "title": gs.BADGES[b][0], "desc": gs.BADGES[b][1]} for b in new]


def overview(lang: str = "en") -> dict:
    """The hub: progress, what's available today, and the 12 boss tiles with the person's current mastery."""
    s = gs.get()
    items = gp.build_pool(lang)
    mastery = {r["tactic"]: r for r in model.all_mastery()}
    return {
        **gs.summary(s, lang),
        "yours_available": sum(1 for i in items if i.source == "yours"),
        "tricks": [{"id": t, "label": tactic_text(t, "label", lang, TACTICS), "blurb": tactic_text(t, "blurb", lang, TACTICS), "level": mastery[t]["level"], "bars": model.LEVEL_BARS[mastery[t]["level"]],
                    "won": t in s["boss_won"], "messages": sum(1 for i in items if i.truth == "scam" and t in i.tactics)} for t, v in TACTICS.items()],
        "resilience": model.baitproof_score(),
    }
