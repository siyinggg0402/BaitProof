"""Short-lived, in-memory cache of finished checks so the live view can fetch the rendered result.
Scoped to the visitor's profile; nothing is written to disk (the message text never leaves memory)."""
from __future__ import annotations

import time
from collections import OrderedDict

from core.domain.schemas import CheckResult
from core.storage import db

TTL, MAX = 600.0, 500
_store: "OrderedDict[str, tuple[float, str, CheckResult]]" = OrderedDict()


def _scope() -> str:
    return db._profile.get() or ""


def put(result: CheckResult) -> None:
    now = time.time()
    while _store and (len(_store) >= MAX or now - next(iter(_store.values()))[0] > TTL):
        _store.popitem(last=False)
    _store[result.check_id] = (now, _scope(), result)


def get(check_id: str) -> CheckResult | None:
    hit = _store.get(check_id)
    if not hit or time.time() - hit[0] > TTL or hit[1] != _scope():
        return None
    return hit[2]
