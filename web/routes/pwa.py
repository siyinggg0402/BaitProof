"""Baitproof as an app you can install, and the phone's Share menu: share a message or a screenshot from WhatsApp (or anywhere) straight into a check.

Android's Share menu lists an installed web app that declares a `share_target` in its manifest. The phone POSTs what was shared to /share. A POST that arrives
from the system may not carry our cookie, so /share does not answer with a page: it keeps the shared words (or picture) in memory for a few minutes, under a
random token, and redirects to /?share=TOKEN, an ordinary page load that carries the person's own cookie. Nothing shared is written to disk or logged, and a
token works once. (iPhones have no share targets for web apps: there, forward the message to the Telegram bot, or paste it.)"""
from __future__ import annotations

import json
import secrets
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response

from core.inputs import image
from web.deps import limit_expensive
from web.uploads import UploadError, read_upload

router = APIRouter()
STATIC = Path(__file__).resolve().parents[1] / "static"
TTL = 300.0  # seconds a shared item waits for its redirect
MAX_ITEMS = 20  # how many may wait at once (a picture can be megabytes, and all of it is in memory)
TEXT_MAX = 4000  # the same limit as the message box
_stash: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()

MANIFEST = {
    "name": "Baitproof", "short_name": "Baitproof", "lang": "en",
    "description": "Check a suspicious message, learn the trick, and keep your family safe. Share a message from WhatsApp straight to Baitproof.",
    "id": "/", "start_url": "/", "scope": "/", "display": "standalone", "orientation": "portrait-primary",
    "background_color": "#FAF8FF", "theme_color": "#7A5CD0",
    "icons": [
        {"src": "/static/img/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": "/static/img/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        {"src": "/static/img/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
    ],
    "share_target": {
        "action": "/share", "method": "POST", "enctype": "multipart/form-data",
        "params": {"title": "title", "text": "text", "url": "url", "files": [{"name": "image", "accept": ["image/*"]}]},
    },
}


@router.get("/manifest.webmanifest")
def manifest() -> Response:
    return Response(json.dumps(MANIFEST, ensure_ascii=False), media_type="application/manifest+json", headers={"Cache-Control": "no-cache"})


@router.get("/sw.js")
def service_worker() -> Response:
    """Served from the site root so that it can cover the whole site (a file under /static/ could only cover /static/)."""
    return Response((STATIC / "sw.js").read_text(encoding="utf-8"), media_type="application/javascript", headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"})


def _purge(now: float) -> None:
    for k in [k for k, (t, _) in _stash.items() if now - t > TTL]:
        del _stash[k]


def keep(item: dict) -> str | None:
    """Hold a shared item for its redirect; the token, or None when too many are already waiting."""
    now = time.time()
    with _lock:
        _purge(now)
        if len(_stash) >= MAX_ITEMS:
            return None
        token = secrets.token_urlsafe(16)
        _stash[token] = (now, item)
        return token


def take(token: str) -> dict | None:
    """The item for this token, once (it is forgotten as it is taken), if it is still fresh."""
    with _lock:
        _purge(time.time())
        got = _stash.pop(token or "", None)
    return got[1] if got else None


def words_of(fields: dict[str, str]) -> str:
    """What the share sheet sent as words: the text, with a title or address added only if the text does not already carry it."""
    parts: list[str] = []
    for key in ("title", "text", "url"):
        v = " ".join((fields.get(key) or "").split()) if key != "text" else (fields.get(key) or "").strip()
        if not v or any(v in p for p in parts):
            continue  # already said by something we have
        parts = [p for p in parts if p not in v] + [v]  # and a longer piece replaces the shorter ones it contains (a title that is the start of the text)
    return "\n".join(parts)[:TEXT_MAX]


@router.post("/share", dependencies=[Depends(limit_expensive)])
async def share(request: Request) -> RedirectResponse:
    try:
        up = await read_upload(request, image.MAX_BYTES, file_field="image", field_max=TEXT_MAX, require_file=False)
    except UploadError as e:
        return RedirectResponse("/?shared=" + ("too_big" if e.reason == "too_big" else "empty"), status_code=303)
    text = words_of(up.fields)
    if not text and not up.data:
        return RedirectResponse("/?shared=empty", status_code=303)
    token = keep({"text": text, "image": up.data or None})
    return RedirectResponse(f"/?share={token}" if token else "/?shared=busy", status_code=303)
