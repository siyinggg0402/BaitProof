"""Personal model: per-tactic mastery + the transparent Baitproof score (PLAN §6b)."""
from __future__ import annotations

from datetime import timedelta

from core.storage import db
from core.domain.i18n import norm, tactic_text, tr
from core.domain.schemas import Level
from core.domain.tactics import TACTICS, valid

LEVEL_POINTS = {"untested": 0.0, "weak": 0.25, "learning": 0.6, "strong": 1.0}
LEVEL_BARS = {"untested": 0, "weak": 1, "learning": 3, "strong": 5}
LEVEL_TEXT = {"untested": "not yet tested", "weak": "weak", "learning": "getting there", "strong": "strong"}
LEVEL_KEYS = {k: f"Level: {v}" for k, v in LEVEL_TEXT.items()}  # translation keys for the same words ("weak" alone is also used for evidence strength)
INTERVAL_DAYS = {"weak": 1, "learning": 3, "strong": 7}


def next_state(level: str, streak: int, outcome: str) -> tuple[str, int]:
    """Honest forgetting: a miss demotes; strong needs two wins in a row after learning."""
    if outcome == "correct":
        if level in ("untested", "weak"):
            return Level.LEARNING.value, 1
        if level == "learning":
            return (Level.STRONG.value, streak + 1) if streak + 1 >= 2 else (level, streak + 1)
        return level, streak + 1
    if outcome == "incorrect":
        return {"strong": "learning"}.get(level, "weak"), 0
    return ("weak" if level == "untested" else level), streak  # partial


def _ensure(conn) -> None:
    for t in TACTICS:
        conn.execute("INSERT OR IGNORE INTO mastery(tactic) VALUES(?)", (t,))


def all_mastery() -> list[dict]:
    with db.connect() as c:
        _ensure(c)
        rows = {r["tactic"]: dict(r) for r in c.execute("SELECT * FROM mastery")}
    return [rows[t] for t in TACTICS]


def record_exposure(tactics: list[str]) -> None:
    """A tactic was seen in a REAL forwarded message: raises its salience for the next drill."""
    with db.connect() as c:
        _ensure(c)
        for t in tactics:
            if valid(t):
                c.execute("UPDATE mastery SET exposure=exposure+1, last_seen=? WHERE tactic=?", (db.iso(db.now()), t))


def record_result(tactic: str, outcome: str) -> None:
    now = db.now()
    with db.connect() as c:
        _ensure(c)
        r = c.execute("SELECT * FROM mastery WHERE tactic=?", (tactic,)).fetchone()
        level, streak = next_state(r["level"], r["streak"], outcome)
        due = now if outcome == "incorrect" or level not in INTERVAL_DAYS else now + timedelta(days=INTERVAL_DAYS[level])
        c.execute(
            "UPDATE mastery SET level=?, streak=?, success=success+?, fail=fail+?, last_tested=?, due=? WHERE tactic=?",
            (level, streak, outcome == "correct", outcome == "incorrect", db.iso(now), db.iso(due), tactic),
        )
    s = baitproof_score()
    with db.connect() as c:
        c.execute("INSERT INTO history(ts,tactic,outcome,score) VALUES(?,?,?,?)", (db.iso(now), tactic, outcome, s))


def _recency(last_tested: str | None) -> float:
    ts = db.parse(last_tested)
    if not ts:
        return 0.0
    days = (db.now() - ts).days
    return 1.0 if days <= 7 else max(0.6, 1 - (days - 7) * 0.4 / 23)


def baitproof_score(rows: list[dict] | None = None) -> int:
    """mean over ALL tactics of mastery points x recency. Untested counts 0, so coverage matters."""
    rows = rows or all_mastery()
    total = sum(LEVEL_POINTS[r["level"]] * _recency(r["last_tested"]) for r in rows)
    return round(100 * total / len(rows))


def due_count(rows: list[dict] | None = None) -> int:
    """Tricks you've practised that are due for a spaced-repetition review."""
    now = db.now()
    return sum(1 for r in (rows or all_mastery()) if r["level"] != "untested" and (d := db.parse(r["due"])) and d <= now)


def resilience_map(lang: str = "en") -> dict:
    lang = norm(lang)
    rows = all_mastery()
    return {
        "score": baitproof_score(rows),
        "due": due_count(rows),
        "tactics": [
            {"id": r["tactic"], "label": tactic_text(r["tactic"], "label", lang, TACTICS), "level": r["level"],
             "level_text": LEVEL_TEXT[r["level"]] if lang == "en" else tr(LEVEL_KEYS[r["level"]], lang), "bars": LEVEL_BARS[r["level"]]}
            for r in rows
        ],
    }
