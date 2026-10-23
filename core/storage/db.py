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
-- shared only: family alerts (a helper's chat is told when a protected person checks something that looks like a scam; never the message itself)
CREATE TABLE IF NOT EXISTS guard_codes(code TEXT PRIMARY KEY, profile TEXT NOT NULL, chat_id TEXT NOT NULL, name TEXT NOT NULL DEFAULT '', created REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0);
-- shared only: a profile can become an account (`profile` is the visitor's cookie id and must NEVER leave the server; `pub` is the id other people see; a nickname, an avatar, a code to be found by friends, a sign-in key kept only as a hash), friends, and game runs for the leaderboard
CREATE TABLE IF NOT EXISTS accounts(profile TEXT PRIMARY KEY, pub TEXT NOT NULL UNIQUE, nickname TEXT NOT NULL, avatar TEXT NOT NULL, friend_code TEXT NOT NULL UNIQUE, key_hash TEXT NOT NULL UNIQUE, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS friendships(a TEXT NOT NULL, b TEXT NOT NULL, since TEXT NOT NULL, PRIMARY KEY(a, b));
CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY AUTOINCREMENT, profile TEXT NOT NULL, game TEXT NOT NULL, score INTEGER NOT NULL, correct INTEGER NOT NULL DEFAULT 0, ts TEXT NOT NULL,
  path TEXT NOT NULL DEFAULT '', skin TEXT NOT NULL DEFAULT '');  -- path: one letter per gate (c right, p careful, w wrong) so a friend's drive can be replayed as a ghost; skin: 'car:hat'
CREATE INDEX IF NOT EXISTS runs_by_profile ON runs(profile, game, ts);
-- shared only: a family group (parents and kids, say): its members, and the scams they chose to share (the same REDACTED text the library keeps, never a raw message)
CREATE TABLE IF NOT EXISTS family_groups(id TEXT PRIMARY KEY, name TEXT NOT NULL, code TEXT NOT NULL UNIQUE, owner TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS family_members(group_id TEXT NOT NULL, profile TEXT NOT NULL UNIQUE, since TEXT NOT NULL, share INTEGER NOT NULL DEFAULT 1, PRIMARY KEY(group_id, profile));  -- share: this person lets the family see their practice progress (never messages)
CREATE TABLE IF NOT EXISTS family_scams(id INTEGER PRIMARY KEY AUTOINCREMENT, group_id TEXT NOT NULL, text TEXT NOT NULL, tactics TEXT NOT NULL, tell_phrase TEXT NOT NULL DEFAULT '',
  tell TEXT NOT NULL DEFAULT '', action TEXT NOT NULL DEFAULT '', by_profile TEXT NOT NULL, created TEXT NOT NULL, UNIQUE(group_id, text));
-- shared only: browsers that asked to be told when a friend passes them (Web Push). The endpoint and its keys belong to the browser; they are never shown to anyone
CREATE TABLE IF NOT EXISTS push_subs(id INTEGER PRIMARY KEY AUTOINCREMENT, profile TEXT NOT NULL, endpoint TEXT NOT NULL UNIQUE, p256dh TEXT NOT NULL, auth TEXT NOT NULL, lang TEXT NOT NULL DEFAULT 'en', created TEXT NOT NULL);
-- shared only: who beat whom in a live race, one row per pair (a < b), for the head-to-head record between two people
CREATE TABLE IF NOT EXISTS duel_pairs(a TEXT NOT NULL, b TEXT NOT NULL, winner TEXT NOT NULL, ts TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS duel_pairs_ab ON duel_pairs(a, b);
CREATE TABLE IF NOT EXISTS guardians(chat_id TEXT NOT NULL, profile TEXT NOT NULL, name TEXT NOT NULL DEFAULT '', lang TEXT NOT NULL DEFAULT 'en', since TEXT NOT NULL, PRIMARY KEY(chat_id, profile));
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


@contextmanager
def as_profile(pid: str):
    """Look at another person's own database for a moment (to read the progress they chose to share). The previous profile is put back afterwards."""
    token = _profile.set(pid if pid and PROFILE_RE.fullmatch(pid) else None)
    try:
        yield
    finally:
        _profile.reset(token)


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


def _migrate(conn) -> None:
    """A database made by an earlier version gets the columns added since (CREATE TABLE IF NOT EXISTS never changes an existing table)."""
    have = {r["name"] for r in conn.execute("PRAGMA table_info(runs)")}
    for column in ("path", "skin"):
        if column not in have:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
    if "share" not in {r["name"] for r in conn.execute("PRAGMA table_info(family_members)")}:
        conn.execute("ALTER TABLE family_members ADD COLUMN share INTEGER NOT NULL DEFAULT 1")
    if conn.execute("SELECT 1 FROM accounts WHERE avatar NOT GLOB '[a-z]*' LIMIT 1").fetchone():  # emoji avatars from before the pictures were drawn
        from core.storage.accounts import LEGACY_AVATARS

        for emoji, name in LEGACY_AVATARS.items():
            conn.execute("UPDATE accounts SET avatar=? WHERE avatar=?", (name, emoji))
        conn.execute("UPDATE accounts SET avatar='fish' WHERE avatar NOT GLOB '[a-z]*'")


@contextmanager
def connect(shared: bool = False):
    """shared=True: the global DB (challenges, which a different person must be able to open)."""
    conn = sqlite3.connect(db_path(shared))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
