"""A local copy of a public list of known phishing sites, so "is this address known to be a scam?" is answered on this machine.

The list is Phishing.Database (https://github.com/Phishing-Database/Phishing.Database, MIT, community-curated, active domains only, about 390k names).
It is downloaded once a day by a background thread (never while a check is running), stored as a SQLite file under BAITPROOF_CACHE_DIR, and swapped in
atomically. A lookup is a local read: the address from the message is never sent anywhere, and the scammer's server is never contacted.

Nothing here decides anything. A hit becomes one piece of evidence in the ledger like any other tool result; a missing list simply means "no answer"."""
from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen

SOURCE = "https://raw.githubusercontent.com/Phishing-Database/Phishing.Database/master/phishing-domains-ACTIVE.txt"
MAX_AGE = 24 * 3600  # seconds before the local copy counts as stale
CHECK_EVERY = 6 * 3600  # how often the background thread looks at the age
MAX_BYTES = 40_000_000  # the list is about 11 MB; a response far past that is not the list
FETCH_TIMEOUT = 60
# Sites where anyone can open a page under someone else's name. A listed page there says nothing about the rest of the site, so only the exact name matches.
SHARED_HOSTING = {
    "github.io", "gitlab.io", "web.app", "firebaseapp.com", "pages.dev", "workers.dev", "netlify.app", "vercel.app", "herokuapp.com", "glitch.me",
    "repl.co", "blogspot.com", "wordpress.com", "weebly.com", "weeblysite.com", "wixsite.com", "000webhostapp.com", "azurewebsites.net",
    "cloudfront.net", "s3.amazonaws.com", "appspot.com", "onrender.com", "fly.dev", "framer.website", "webflow.io", "carrd.co", "sites.google.com",
}
# Sites where anyone gets a page at a PATH under a name everybody shares. The list does carry some of them (a phishing page was once hosted there), but the name
# alone says nothing about the page, and a warning on every link to them would be wrong far more often than right.
PATH_HOSTING = {
    "sites.google.com", "docs.google.com", "drive.google.com", "forms.gle", "forms.office.com", "storage.googleapis.com", "cloudflare-ipfs.com", "ipfs.io",
    "dweb.link", "ipfs.dweb.link", "dl.dropboxusercontent.com", "1drv.ms", "onedrive.live.com", "notion.site", "typeform.com", "linktr.ee", "canva.com",
}
_NAME = re.compile(r"^[a-z0-9]([a-z0-9._-]{0,251}[a-z0-9])?$")
_lock = threading.Lock()
_started = False


def exempt(host: str) -> bool:
    """True for a name the list's verdict must not be applied to: an open hosting platform (see SHARED_HOSTING and PATH_HOSTING)."""
    return host in SHARED_HOSTING or host in PATH_HOSTING


def enabled() -> bool:
    return os.getenv("BAITPROOF_BLOCKLIST", "1") == "1"


def cache_dir() -> Path:
    return Path(os.getenv("BAITPROOF_CACHE_DIR", "data/cache"))


def db_path() -> Path:
    return cache_dir() / "phishing-domains.sqlite"


def available() -> bool:
    return enabled() and db_path().is_file()


def age_seconds() -> float | None:
    """How old the local copy is, or None when there is none."""
    try:
        return max(0.0, time.time() - db_path().stat().st_mtime)
    except OSError:
        return None


def stale() -> bool:
    a = age_seconds()
    return a is None or a > MAX_AGE


def size() -> int:
    """How many names the local copy holds (0 when there is none)."""
    if not available():
        return 0
    try:
        con = sqlite3.connect(f"file:{db_path()}?mode=ro", uri=True)
        try:
            return int(con.execute("SELECT COUNT(*) FROM domains").fetchone()[0])
        finally:
            con.close()
    except sqlite3.Error:
        return 0


def lookup(names: list[str]) -> str:
    """The first of `names` that is on the list ('' when none is, or when there is no list). The caller decides which names to ask about."""
    if not names or not available():
        return ""
    try:
        con = sqlite3.connect(f"file:{db_path()}?mode=ro", uri=True)
        try:
            for n in names:
                if con.execute("SELECT 1 FROM domains WHERE host = ? LIMIT 1", (n,)).fetchone():
                    return n
        finally:
            con.close()
    except sqlite3.Error:
        return ""  # a damaged or half-written file is a missing list, never a crash
    return ""


def parse(text: str) -> list[str]:
    """Host names from a one-per-line list: lower-cased, de-duplicated, anything that is not shaped like a host name dropped."""
    seen: dict[str, None] = {}
    for line in text.splitlines():
        h = line.strip().lower().rstrip(".")
        if h.startswith("www."):
            h = h[4:]
        if "." in h and _NAME.match(h):
            seen[h] = None
    return list(seen)


def install(hosts: list[str]) -> int:
    """Write `hosts` as the local copy, replacing the old one in a single atomic step. Returns how many were stored."""
    cache_dir().mkdir(parents=True, exist_ok=True)
    tmp = db_path().with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    try:
        con.execute("CREATE TABLE domains (host TEXT PRIMARY KEY) WITHOUT ROWID")
        con.executemany("INSERT OR IGNORE INTO domains VALUES (?)", ((h,) for h in hosts))
        con.commit()
    finally:
        con.close()
    os.replace(tmp, db_path())
    return len(hosts)


def _fetch() -> str:
    req = Request(SOURCE, headers={"User-Agent": "Baitproof/1.0 (scam-defense; refreshes a public phishing list once a day)"})
    with urlopen(req, timeout=FETCH_TIMEOUT) as r:  # noqa: S310 (fixed https address)
        raw = r.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("the list is far larger than expected")
    return raw.decode("utf-8", "replace")


def refresh(force: bool = False, fetch=_fetch) -> int | None:
    """Download and install the list when it is missing or stale (or `force`). Returns how many names were stored, or None when nothing was done.
    Raises on a failed download or an implausibly small list; the old copy is then kept."""
    with _lock:
        if not force and not stale():
            return None
        hosts = parse(fetch())
        if len(hosts) < 1000:  # an error page or a truncated download must never replace a good list
            raise ValueError(f"the downloaded list has only {len(hosts)} names")
        return install(hosts)


def _loop() -> None:
    while True:
        try:
            refresh()
        except Exception:  # offline, blocked, a bad download: keep the copy we have and try again later
            pass
        time.sleep(CHECK_EVERY)


def start_background() -> bool:
    """Keep the local copy fresh for as long as the process lives. A no-op when the list or the network tools are switched off, and when already started."""
    global _started
    if _started or not enabled() or os.getenv("BAITPROOF_NET_TOOLS", "1") != "1":
        return False
    _started = True
    threading.Thread(target=_loop, name="bp-blocklist", daemon=True).start()
    return True
