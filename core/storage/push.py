"""Web Push: a friend who asked is told, on their phone or computer, that someone has just passed their best on Scam Road. It is opt-in per browser, needs the
site's own VAPID keys (without them the whole feature stays off and nothing on the page mentions it), and never carries more than a nickname and a distance.
A browser's subscription (an address on its push service, plus two keys) is kept only to send to, only for people who have a profile, and only to browsers'
own push services (an allow-list, so the server can never be pointed at an address of someone's choosing). Lives in the SHARED database."""
from __future__ import annotations

import importlib.util
import json
import os
import threading
import time
from collections import defaultdict, deque
from urllib.parse import urlsplit

from core.lang.i18n import norm, tr
from core.storage import accounts, db

MAX_PER_HOUR = 3        # nudges one person can get in an hour, however many friends pass them
MAX_DEVICES = 5
SYNC = False            # tests send in the calling thread
ALLOWED_HOSTS = ("fcm.googleapis.com", "push.services.mozilla.com", "notify.windows.com", "push.apple.com")  # Chrome/Edge/Android, Firefox, Windows, Safari
_sent: dict[str, deque] = defaultdict(deque)


class PushError(ValueError):
    pass


def enabled() -> bool:
    return bool(os.getenv("VAPID_PRIVATE_KEY") and os.getenv("VAPID_PUBLIC_KEY") and importlib.util.find_spec("pywebpush"))


def public_key() -> str:
    return os.getenv("VAPID_PUBLIC_KEY", "") if enabled() else ""


def _endpoint_ok(endpoint: str) -> bool:
    u = urlsplit(endpoint)
    host = (u.hostname or "").lower()
    return u.scheme == "https" and len(endpoint) < 1200 and not u.username and any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS)


def subscribe(profile: str, endpoint: str, p256dh: str, auth: str, lang: str = "en") -> None:
    if accounts.get(profile) is None:
        raise PushError("Make a profile first to get notifications.")
    if not _endpoint_ok(endpoint) or not (10 < len(p256dh) < 200) or not (5 < len(auth) < 100):
        raise PushError("That doesn't look like a browser's notification address.")
    with db.connect(shared=True) as c:
        mine = c.execute("SELECT COUNT(*) AS n FROM push_subs WHERE profile=? AND endpoint<>?", (profile, endpoint)).fetchone()["n"]
        if mine >= MAX_DEVICES:
            raise PushError("This profile already has notifications on five devices. Turn one off first.")
        c.execute("INSERT INTO push_subs(profile,endpoint,p256dh,auth,lang,created) VALUES(?,?,?,?,?,?) ON CONFLICT(endpoint) DO UPDATE SET profile=excluded.profile, "
                  "p256dh=excluded.p256dh, auth=excluded.auth, lang=excluded.lang", (profile, endpoint, p256dh, auth, norm(lang), db.iso(db.now())))


def unsubscribe(profile: str, endpoint: str) -> bool:
    with db.connect(shared=True) as c:
        return c.execute("DELETE FROM push_subs WHERE profile=? AND endpoint=?", (profile, endpoint)).rowcount > 0


def count(profile: str) -> int:
    with db.connect(shared=True) as c:
        return c.execute("SELECT COUNT(*) AS n FROM push_subs WHERE profile=?", (profile,)).fetchone()["n"]


def _subs(profile: str) -> list[dict]:
    with db.connect(shared=True) as c:
        return [dict(r) for r in c.execute("SELECT * FROM push_subs WHERE profile=?", (profile,)).fetchall()]


def _drop(endpoint: str) -> None:
    with db.connect(shared=True) as c:
        c.execute("DELETE FROM push_subs WHERE endpoint=?", (endpoint,))


def _send(sub: dict, payload: dict) -> bool:
    """Send one notification. False means the browser has gone (its subscription is removed); other failures are tried again next time."""
    from pywebpush import WebPushException, webpush

    try:
        webpush(subscription_info={"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}}, data=json.dumps(payload, ensure_ascii=False),
                vapid_private_key=os.environ["VAPID_PRIVATE_KEY"], vapid_claims={"sub": os.getenv("VAPID_SUBJECT", "mailto:admin@example.com")}, ttl=3600, timeout=8)
        return True
    except WebPushException as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        if status in (404, 410):
            _drop(sub["endpoint"])
        return False
    except Exception:
        return False


def _allowed_now(profile: str) -> bool:
    now, q = time.monotonic(), _sent[profile]
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= MAX_PER_HOUR:
        return False
    q.append(now)
    return True


def _payload(name: str, distance: int, mine: int, game: str, lang: str) -> dict:
    daily = game == "daily"
    body = tr("They drove {n} m on today's Daily Road. Your best is {mine} m. Take the wheel and win it back!" if daily else
              "They drove {n} m on Scam Road. Your best is {mine} m. Take the wheel and win it back!", lang, n=distance, mine=mine)
    return {"title": "🏁 " + tr("{name} just passed your best!", lang, name=name), "body": body, "url": "/road?daily=1" if daily else "/road", "tag": "baitproof-pass"}


def _deliver(jobs: list[tuple[dict, dict]]) -> None:
    for sub, payload in jobs:
        _send(sub, payload)


def notify_passed(owner: str, recipients: list[tuple[str, int]], distance: int, game: str) -> int:
    """Tell each friend who has asked (and is not over their hourly limit) that `owner` has just driven `distance` m past their best. Returns how many were queued.
    Best effort: it never raises and never makes the drive's result wait."""
    if not enabled() or not recipients:
        return 0
    try:
        card = accounts.get(owner)
        if card is None:
            return 0
        jobs = []
        for profile, mine in recipients:
            if profile == owner:
                continue
            subs = _subs(profile)
            if subs and _allowed_now(profile):
                jobs += [(s, _payload(card["nickname"], distance, mine, game, s["lang"])) for s in subs]
        if not jobs:
            return 0
        if SYNC:
            _deliver(jobs)
        else:
            threading.Thread(target=_deliver, args=(jobs,), daemon=True).start()
        return len(jobs)
    except Exception:
        return 0


def send_test(profile: str) -> int:
    """A test notification to this person's own devices (so they can see it work). Returns how many were sent."""
    if not enabled():
        return 0
    n = 0
    for s in _subs(profile):
        if _send(s, {"title": "🏁 " + tr("Notifications are on", s["lang"]), "body": tr("You'll be told here when a friend passes your best on Scam Road.", s["lang"]), "url": "/friends", "tag": "baitproof-test"}):
            n += 1
    return n


_nudged: dict[tuple[str, str], float] = {}
NUDGE_GAP = 20 * 3600   # one nudge a day, from one person to another


def notify_nudge(sender: str, target: str) -> str:
    """A friendly nudge to practise, from one family member to another. Returns "sent", "nopush" (their devices cannot be reached: nothing was sent) or "limit"."""
    if not enabled():
        return "nopush"
    subs, card = _subs(target), accounts.get(sender)
    if not subs or card is None:
        return "nopush"
    now = time.monotonic()
    if now - _nudged.get((sender, target), -NUDGE_GAP) < NUDGE_GAP:
        return "limit"
    _nudged[(sender, target)] = now
    jobs = [(s, {"title": "🐟 " + tr("{name} is thinking of you", s["lang"], name=card["nickname"]), "body": tr("A minute of practice keeps the whole family safer. Open Baitproof?", s["lang"]),
                 "url": "/train", "tag": "baitproof-nudge"}) for s in subs]
    if SYNC:
        _deliver(jobs)
    else:
        threading.Thread(target=_deliver, args=(jobs,), daemon=True).start()
    return "sent"


def notify_challenge(host: str, targets: list[str], code: str) -> int:
    """Tell friends who have notifications on that someone has opened a live race and asked them in. Best effort; returns how many messages were queued."""
    if not enabled() or not targets:
        return 0
    try:
        card = accounts.get(host)
        if card is None:
            return 0
        jobs = []
        for profile in targets:
            subs = _subs(profile)
            if subs and _allowed_now("race:" + profile):
                jobs += [(s, {"title": "🏁 " + tr("{name} challenges you to a live race!", s["lang"], name=card["nickname"]), "body": tr("Tap to join the lobby before it starts.", s["lang"]),
                              "url": f"/duel/{code}", "tag": "baitproof-race"}) for s in subs]
        if not jobs:
            return 0
        if SYNC:
            _deliver(jobs)
        else:
            threading.Thread(target=_deliver, args=(jobs,), daemon=True).start()
        return len(jobs)
    except Exception:
        return 0
