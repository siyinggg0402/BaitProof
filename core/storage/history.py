"""One record of every check a person has run, from any channel (web or Telegram), kept in their own profile.
Privacy: the verdict, the tricks and the giveaway are stored; of the message itself only a short REDACTED preview (and the person can turn
even that off, or delete any record, or all of them). The raw message is never stored."""
from __future__ import annotations

import json
import os
import re

from core.domain.privacy import redact
from core.domain.schemas import CheckResult
from core.storage import db

KEEP = 500  # newest records kept per person
PREVIEW_LEN = 120
CHANNELS = ("web", "telegram")


def get_setting(key: str, default: str = "") -> str:
    with db.connect() as c:
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


def set_setting(key: str, value: str) -> None:
    with db.connect() as c:
        c.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def preview_enabled() -> bool:
    return get_setting("store_preview", os.getenv("BAITPROOF_STORE_PREVIEW", "1")) == "1"


def make_preview(text: str) -> str:
    t = re.sub(r"\s+", " ", redact(text)).strip()
    return t if len(t) <= PREVIEW_LEN else t[: PREVIEW_LEN - 1].rstrip() + "…"


def add(result: CheckResult, channel: str, text: str) -> None:
    """Record one finished check. Safe to call twice for the same check (the id is unique)."""
    if channel not in CHANNELS or not result.check_id:
        return
    preview = make_preview(text) if preview_enabled() else ""
    with db.connect() as c:
        c.execute(
            "INSERT OR IGNORE INTO check_log(id,ts,channel,verdict,confidence,headline,tell,action,tactics,preview,trained) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (result.check_id, db.iso(db.now()), channel, result.verdict.value, result.confidence, result.headline, result.tell[:400], result.action[:400],
             json.dumps([t.id for t in result.tactics]), preview, 1 if result.added_to_training else 0))
        c.execute("DELETE FROM check_log WHERE id NOT IN (SELECT id FROM check_log ORDER BY ts DESC LIMIT ?)", (KEEP,))


def _row(r) -> dict:
    d = dict(r)
    d["tactics"] = json.loads(d["tactics"])
    d["trained"] = bool(d["trained"])
    return d


def list_checks(limit: int = 100, channel: str | None = None, verdict: str | None = None) -> list[dict]:
    q, args = "SELECT * FROM check_log", []
    where = []
    if channel in CHANNELS:
        where.append("channel=?"), args.append(channel)
    if verdict:
        where.append("verdict=?"), args.append(verdict)
    if where:
        q += " WHERE " + " AND ".join(where)
    with db.connect() as c:
        return [_row(r) for r in c.execute(q + " ORDER BY ts DESC LIMIT ?", (*args, max(1, min(limit, KEEP))))]


def delete(check_id: str) -> bool:
    with db.connect() as c:
        return c.execute("DELETE FROM check_log WHERE id=?", (check_id,)).rowcount > 0


def delete_all() -> int:
    with db.connect() as c:
        return c.execute("DELETE FROM check_log").rowcount


def stats() -> dict:
    rows = list_checks(KEEP)
    tricks: dict[str, int] = {}
    for r in rows:
        for t in r["tactics"]:
            tricks[t] = tricks.get(t, 0) + 1
    flagged = [r for r in rows if r["verdict"] in ("scam", "likely_scam")]
    return {
        "total": len(rows),
        "flagged": len(flagged),
        "by_channel": {ch: sum(1 for r in rows if r["channel"] == ch) for ch in CHANNELS},
        "top_tricks": sorted(tricks.items(), key=lambda kv: -kv[1])[:5],
    }
