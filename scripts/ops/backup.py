"""One compressed backup of everything the site keeps (the shared database and every visitor profile), made with SQLite's own backup so it is consistent while the site runs.
Keeps the newest --keep files. It sits on the same disk as the data, so it guards against mistakes, not against losing the server: copy the newest one to your own machine now and then
(deploy/README.md says how).
Usage: python -m scripts.ops.backup [--out DIR] [--keep 7]"""
import argparse
import os
import sqlite3
import tarfile
import tempfile
from contextlib import closing
from datetime import datetime
from pathlib import Path

import core  # noqa: F401  loads .env


def snapshot(src: Path, dst: Path) -> None:
    with closing(sqlite3.connect(f"file:{src}?mode=ro", uri=True)) as a, closing(sqlite3.connect(dst)) as b:
        a.backup(b)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="where to put the backups (default: a backups folder beside the database)")
    ap.add_argument("--keep", type=int, default=7)
    a = ap.parse_args()
    shared = Path(os.getenv("BAITPROOF_DB", "baitproof.sqlite")).resolve()
    if not shared.exists():
        print(f"nothing to back up: no {shared}")
        return 0
    out = Path(a.out) if a.out else shared.parent / "backups"
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"baitproof-{datetime.now():%Y-%m-%d-%H%M}.tar.gz"
    sources = [(shared, shared.name)] + [(f, f"profiles/{f.name}") for f in sorted((shared.parent / "profiles").glob("*.sqlite"))]
    with tempfile.TemporaryDirectory() as tmp, tarfile.open(target, "w:gz") as tar:
        for i, (src, name) in enumerate(sources):
            copy = Path(tmp) / f"{i}.sqlite"
            try:
                snapshot(src, copy)
            except sqlite3.Error as e:  # one unreadable profile must not lose the rest
                print(f"skipped {name}: {e}")
                continue
            tar.add(copy, arcname=name)
    for old in sorted(out.glob("baitproof-*.tar.gz"))[:-a.keep]:
        old.unlink()
    print(f"{target} ({target.stat().st_size / 1e6:.1f} MB, {len(sources)} databases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
