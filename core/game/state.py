"""A person's game progress, kept in their own profile: XP, level, streak, badges. (The friends' leaderboard is separate: core/storage/runs.py.)"""
from __future__ import annotations

import json
import math
from datetime import timedelta

from core.lang.i18n import norm, tactic_text, tr
from core.domain.tactics import TACTICS
from core.storage import db

DEFAULT = {"xp": 0, "rounds": 0, "correct_total": 0, "best_combo": 0, "streak": 0, "best_streak": 0, "last_play": "", "daily_done": "",
           "badges": [], "boss_won": [], "yours_correct": 0, "tells_found": 0, "seen": [], "garage": {"car": "plum", "hat": "none"}, "road_daily_count": 0, "road_daily_last": "",
           "duel_wins": 0, "duels_played": 0}
TITLES = ["Rookie", "Spotter", "Sleuth", "Detective", "Guardian", "Sentinel", "Scam Slayer"]

BADGES: dict[str, tuple[str, str]] = {
    "first-round": ("First steps", "Finish your first round"),
    "perfect-round": ("Flawless", "Finish a round without a single slip"),
    "combo-5": ("On fire", "Get 5 right in a row"),
    "streak-3": ("3-day streak", "Play three days in a row"),
    "streak-7": ("Week warrior", "Play seven days in a row"),
    "daily-first": ("Daily challenger", "Complete a Daily Challenge"),
    "level-3": ("Sleuth", "Reach level 3"),
    "level-5": ("Guardian", "Reach level 5"),
    "yours-5": ("Family detective", "Spot 5 scams that reached your own family"),
    "tell-5": ("Eagle eye", "Find the giveaway in 5 messages"),
    "road-500": ("Road tripper", "Drive 500 metres on Scam Road in one go"),
    "road-ahead": ("Out in front", "Drive past a friend's best on Scam Road"),
    "road-daily": ("Daily driver", "Finish a Daily Road"),
    "link-10": ("Link sleuth", "Spot 10 fake links in one Link Hunt"),
    "duel-win": ("Duelist", "Win a live race"),
    "duel-5": ("Race champion", "Win 5 live races"),
    **{f"boss:{t}": (f"Master of “{v['label']}”", f"Beat the {v['label'].lower()} boss") for t, v in TACTICS.items()},
}


def get() -> dict:
    with db.connect() as c:
        rows = {r["key"]: json.loads(r["value"]) for r in c.execute("SELECT key,value FROM game")}
    return {**DEFAULT, **{k: v for k, v in rows.items() if k in DEFAULT}}


def save(state: dict) -> None:
    with db.connect() as c:
        for k in DEFAULT:
            c.execute("INSERT INTO game(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, json.dumps(state[k])))


def level_for(xp: int) -> int:
    """Level n starts at 50*n*(n-1) XP: 100 for level 2, 300 for 3, 600 for 4 ..."""
    return max(1, int(0.5 + math.sqrt(0.25 + max(0, xp) / 50)))


def xp_for(level: int) -> int:
    return 50 * level * (level - 1)


def title_for(level: int, lang: str = "en") -> str:
    return tr(TITLES[min(level - 1, len(TITLES) - 1)], lang)


def badge_text(bid: str, lang: str = "en") -> tuple[str, str]:
    """(title, description) of a badge in the reader's language. The per-trick 'Master of ...' badges are built from the trick's name."""
    lang = norm(lang)
    if bid.startswith("boss:") and bid[5:] in TACTICS and lang != "en":
        label = tactic_text(bid[5:], "label", lang, TACTICS)
        return tr("Master of “{label}”", lang, label=label), tr("Beat the {label} boss", lang, label=label)
    title, desc = BADGES[bid]
    return tr(title, lang), tr(desc, lang)


def today() -> str:
    return db.now().date().isoformat()


def touch_streak(state: dict) -> None:
    """Call once per finished round: extends the streak if they played yesterday, restarts it if they skipped a day."""
    t = today()
    if state["last_play"] == t:
        return
    yesterday = (db.now().date() - timedelta(days=1)).isoformat()
    state["streak"] = state["streak"] + 1 if state["last_play"] == yesterday else 1
    state["best_streak"] = max(state["best_streak"], state["streak"])
    state["last_play"] = t


def summary(state: dict | None = None, lang: str = "en") -> dict:
    s = state or get()
    lvl = level_for(s["xp"])
    lo, hi = xp_for(lvl), xp_for(lvl + 1)
    streak_alive = s["last_play"] in (today(), (db.now().date() - timedelta(days=1)).isoformat())
    return {"xp": s["xp"], "level": lvl, "title": title_for(lvl, lang), "xp_into_level": s["xp"] - lo, "xp_for_level": hi - lo, "streak": s["streak"] if streak_alive else 0,
            "best_streak": s["best_streak"], "rounds": s["rounds"], "best_combo": s["best_combo"], "daily_done": s["daily_done"] == today(),
            "badges": [{"id": b, "title": badge_text(b, lang)[0], "desc": badge_text(b, lang)[1]} for b in s["badges"] if b in BADGES],
            "badges_total": len(BADGES), "boss_won": s["boss_won"]}
