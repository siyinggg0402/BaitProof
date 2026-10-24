"""Delete the empty visitor profiles that pile up on a public site. Every browser (and every link-preview, crawler and uptime ping) that arrives without a cookie gets
its own ~130 KB database file; most never do anything. A profile is removed only if ALL of these hold: it has not been touched for --days days, nothing in the shared
database mentions it (no account, friend, family group, Telegram chat, game run or push subscription), and it holds no check, practice history or saved scam.
Anything that cannot be read is kept. Without --apply it only reports.
Usage: python -m scripts.ops.prune_profiles [--days 7] [--apply]"""
import argparse
import os
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path

import core  # noqa: F401  loads .env

ID = re.compile(r"[0-9a-f]{32}")
USED = ("history", "check_log", "library")  # tables in a profile's own database that show someone really used it


def referenced(shared: Path) -> set[str]:
    """Every profile id the shared database mentions anywhere (accounts, friendships, groups, runs, Telegram links ...)."""
    found: set[str] = set()
    with closing(sqlite3.connect(f"file:{shared}?mode=ro", uri=True)) as c:
        for (table,) in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            for row in c.execute(f'SELECT * FROM "{table}"'):
                for v in row:
                    if isinstance(v, str):
                        found.update(ID.findall(v))
    return found


def unused(path: Path) -> bool:
    try:
        with closing(sqlite3.connect(f"file:{path}?mode=ro", uri=True)) as c:
            return all(c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0 for t in USED)
    except sqlite3.Error:
        return False  # unreadable or a different layout: keep it


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=7, help="only profiles untouched for this long")
    ap.add_argument("--apply", action="store_true", help="really delete (default: only report)")
    a = ap.parse_args()
    shared = Path(os.getenv("BAITPROOF_DB", "baitproof.sqlite")).resolve()
    folder = shared.parent / "profiles"
    if not shared.exists() or not folder.is_dir():
        print(f"nothing to do: no {shared} or {folder}")
        return 0
    keep_ids, cutoff = referenced(shared), time.time() - a.days * 86400
    files = sorted(folder.glob("*.sqlite"))
    gone = freed = 0
    for f in files:
        if f.stem in keep_ids or f.stat().st_mtime > cutoff or not unused(f):
            continue
        gone, freed = gone + 1, freed + f.stat().st_size
        if a.apply:
            f.unlink(missing_ok=True)
    print(f"{len(files)} profiles; {'removed' if a.apply else 'would remove'} {gone} empty ones older than {a.days:g} days ({freed / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
