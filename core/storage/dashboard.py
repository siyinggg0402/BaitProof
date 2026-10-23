"""The family dashboard: how the people in a family group are doing at spotting scams, built only from what each person has chosen to share (their practice score,
streak and which tricks they have practised: never a message, a check or a name of a scam). It reads each sharing person's own progress database for a moment;
people who do not share appear as a name and nothing else. A profile id is a session cookie: it is used here to read and never put in the result."""
from __future__ import annotations

from datetime import timedelta

from core.domain.tactics import TACTICS
from core.game import state as gs
from core.lang.i18n import tactic_text, tr
from core.storage import db, groups, model

STALE_DAYS = 5          # someone who has not practised for this long (or ever) can be given a nudge
SOFT_SPOTS = 3


def member_stats(profile: str) -> dict:
    """One person's practice progress, read from their own database."""
    with db.as_profile(profile):
        rows = model.all_mastery()
        week = db.iso(db.now() - timedelta(days=7))
        with db.connect() as c:
            last = c.execute("SELECT MAX(ts) AS ts FROM history").fetchone()["ts"]
            drills = c.execute("SELECT COUNT(*) AS n FROM history WHERE ts>=?", (week,)).fetchone()["n"]
        streak = gs.summary()["streak"]
        score = model.baitproof_score(rows)
        due = model.due_count(rows)
    ts = db.parse(last)
    return {"score": score, "streak": streak, "last_active": last, "days_since": (db.now() - ts).days if ts else None, "drills_week": drills, "due": due,
            "levels": {r["tactic"]: r["level"] for r in rows}}


def family(profile: str, lang: str = "en") -> dict | None:
    """The dashboard for the group this person is in, or None if they are in none."""
    people = groups.members_for_dashboard(profile)
    if not people:
        return None
    members, shared = [], []
    for p in people:
        stats = member_stats(p["profile"]) if (p["shares"] or p["you"]) else None
        visible = bool(p["shares"])      # (you always see your own; the family sees you only if you share)
        if stats and (p["shares"]):
            shared.append(stats)
        stale = bool(stats and p["shares"] and not p["you"] and (stats["days_since"] is None or stats["days_since"] >= STALE_DAYS))
        members.append({"pub": p["pub"], "nickname": p["nickname"], "avatar": p["avatar"], "you": p["you"], "owner": p["owner"], "shares": visible, "stats": stats, "needs_nudge": stale})
    tactics = []
    for tid in TACTICS:
        cells = [(m["stats"]["levels"][tid] if (m["stats"] and (m["shares"] or m["you"])) else None) for m in members]
        seen = [model.LEVEL_POINTS[l] for l, m in zip(cells, members) if l is not None and m["shares"]]
        avg = round(100 * sum(seen) / len(seen)) if seen else None
        tactics.append({"id": tid, "label": tactic_text(tid, "label", lang, TACTICS), "avg": avg, "cells": cells,
                        "weak_n": sum(1 for l, m in zip(cells, members) if l in ("untested", "weak") and m["shares"])})
    ranked = sorted((t for t in tactics if t["avg"] is not None), key=lambda t: (t["avg"], -t["weak_n"]))
    soft = [t["id"] for t in ranked[:SOFT_SPOTS] if t["avg"] < 70]
    for t in tactics:
        t["soft"] = t["id"] in soft
    scores = [s["score"] for s in shared]
    return {
        "name": people[0]["family"], "members": members, "tactics": tactics, "soft": [{"id": t["id"], "label": t["label"]} for t in tactics if t["soft"]],
        "summary": {"members": len(members), "sharing": len(shared), "avg_score": round(sum(scores) / len(scores)) if scores else None,
                    "practised_week": sum(1 for s in shared if s["drills_week"] > 0), "drills_week": sum(s["drills_week"] for s in shared), "shared_week": people[0]["shared_week"]},
    }


def summary_text(fam: dict, lang: str = "en") -> str:
    """A few friendly lines for the family chat: how the week went and what to practise next."""
    s = fam["summary"]
    lines = [tr("👪 {family} on Baitproof this week", lang, family=fam["name"])]
    if s["sharing"]:
        lines.append(tr("{n} of {m} practised. Family score: {score} out of 100.", lang, n=s["practised_week"], m=s["sharing"], score=s["avg_score"]))
    if fam["soft"]:
        lines.append(tr("Tricks to practise next: {tricks}.", lang, tricks=", ".join(t["label"] for t in fam["soft"])))
    if s["shared_week"]:
        lines.append(tr("{n} scams shared this week.", lang, n=s["shared_week"]))
    lines.append(tr("A minute of practice keeps everyone safer. 🐟", lang))
    return "\n".join(lines)
