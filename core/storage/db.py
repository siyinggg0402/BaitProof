"""SQLite helper. Stores tactic mastery + abstracted examples only, never raw messages."""
from __future__ import annotations

import os
import re
import sqlite3
from contextvars import ContextVar
from contextlib import contextmanager
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS mastery(
  tactic TEXT PRIMARY KEY, level TEXT NOT NULL DEFAULT 'untested',
  success INTEGER NOT NULL DEFAULT 0, fail INTEGER NOT NULL DEFAULT 0,
  streak INTEGER NOT NULL DEFAULT 0, exposure INTEGER NOT NULL DEFAULT 0,
  last_tested TEXT, last_seen TEXT, due TEXT);
CREATE TABLE IF NOT EXISTS library(
  id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL UNIQUE,
  tactics TEXT NOT NULL, tell_phrase TEXT NOT NULL DEFAULT '',
  tell TEXT NOT NULL DEFAULT '', action TEXT NOT NULL DEFAULT '', created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS history(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, tactic TEXT NOT NULL,
  outcome TEXT NOT NULL, score INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS challenges(
  id TEXT PRIMARY KEY, items TEXT NOT NULL, created TEXT NOT NULL);
-- per-person record of checks from every channel. Stores the verdict, tricks and giveaway, plus (optionally) a short REDACTED preview; never the raw message.
CREATE TABLE IF NOT EXISTS check_log(
  id TEXT PRIMARY KEY, ts TEXT NOT NULL, channel TEXT NOT NULL, verdict TEXT NOT NULL, confidence TEXT NOT NULL,
  headline TEXT NOT NULL DEFAULT '', tell TEXT NOT NULL DEFAULT '', action TEXT NOT NULL DEFAULT '',
  tactics TEXT NOT NULL DEFAULT '[]', preview TEXT NOT NULL DEFAULT '', trained INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS game(key TEXT PRIMARY KEY, value TEXT NOT NULL);
-- shared (global DB) only: linking a Telegram chat to a web profile with a short-lived one-time code
CREATE TABLE IF NOT EXISTS link_codes(code TEXT PRIMARY KEY, profile TEXT NOT NULL, created REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS telegram_links(chat_id TEXT PRIMARY KEY, profile TEXT NOT NULL, linked_at TEXT NOT NULL);
"""


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.isoformat()


def parse(ts: str | None) -> datetime | None:
    return datetime.fromisoformat(ts) if ts else None


# Anonymous per-visitor storage (public deploy). Off unless BAITPROOF_MULTIUSER=1; no accounts, just a cookie id.
_profile: ContextVar[str | None] = ContextVar("profile", default=None)
PROFILE_RE = re.compile(r"[0-9a-f]{32}")


def multiuser() -> bool:
    return os.getenv("BAITPROOF_MULTIUSER") == "1"


def set_profile(pid: str | None) -> None:
    _profile.set(pid if pid and PROFILE_RE.fullmatch(pid) else None)


def db_path(shared: bool = False) -> str:
    base = os.getenv("BAITPROOF_DB", "baitproof.sqlite")
    pid = _profile.get()
    if shared or not multiuser() or not pid:
        return base
    folder = os.path.join(os.path.dirname(os.path.abspath(base)), "profiles")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"{pid}.sqlite")


@contextmanager
def connect(shared: bool = False):
    """shared=True: the global DB (challenges, which a different person must be able to open)."""
    conn = sqlite3.connect(db_path(shared))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
