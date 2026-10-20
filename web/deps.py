"""Cross-cutting web concerns: anonymous per-visitor profiles, rate limiting, security headers."""
from __future__ import annotations

import os
import secrets
import time
from collections import defaultdict, deque
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request

from core.lang import i18n
from core.storage import db

LANG_COOKIE = "lang"
LANG_CODES = {c.lower(): c for c in i18n.LANGS}  # 'zh-hant' -> 'zh-Hant'


def request_lang(request: Request) -> str:
    """The visitor's language: the `lang` cookie (en | zh | zh-Hant), else their browser's Accept-Language, else English."""
    cached = getattr(request.state, "lang", None)
    if cached:
        return cached
    code = LANG_CODES.get(request.cookies.get(LANG_COOKIE, "").lower())
    lang = code or i18n.from_accept_language(request.headers.get("accept-language"))
    request.state.lang = lang
    return lang


def safe_next(target: str | None) -> str:
    """Where to go after switching language: only a path on this site ('/records?channel=web'), never another site."""
    t = target or ""
    if not t.startswith("/") or t.startswith("//") or "\\" in t or any(ord(c) < 32 or ord(c) == 127 for c in t):
        return "/"
    parts = urlsplit(t)
    return t if not parts.scheme and not parts.netloc else "/"


async def bind_profile(request: Request) -> None:
    """Anonymous per-visitor profile (cookie, no accounts) so strangers never share a personal model."""
    if not db.multiuser():
        return
    pid = request.cookies.get("bp", "")
    if not db.PROFILE_RE.fullmatch(pid):
        pid = secrets.token_hex(16)
        request.state.new_profile = pid  # cookie is attached in the middleware (routes return their own Response objects)
    db.set_profile(pid)


HITS: dict[str, deque] = defaultdict(deque)
RATE, WINDOW = int(os.getenv("BAITPROOF_RATE", "30")), 60


async def limit_expensive(request: Request) -> None:
    """Per-IP cap on routes that cost model calls. Behind a proxy, run uvicorn with --proxy-headers."""
    q, now = HITS[request.client.host if request.client else "?"], time.monotonic()
    while q and now - q[0] > WINDOW:
        q.popleft()
    if len(q) >= RATE:
        raise HTTPException(429, "Too many requests. Please wait a minute and try again.")
    q.append(now)


def add_security_headers(app: FastAPI) -> None:
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        resp = await call_next(request)
        if pid := getattr(request.state, "new_profile", None):
            resp.set_cookie("bp", pid, max_age=31536000, httponly=True, samesite="lax", secure=request.url.scheme == "https")
        resp.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'"
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["Referrer-Policy"] = "same-origin"
        if resp.headers.get("content-type", "").startswith("text/html"):
            resp.headers["Vary"] = "Cookie, Accept-Language"  # the page's language depends on both
        return resp


LOGIN_HITS: dict[str, deque] = defaultdict(deque)
LOGIN_RATE = 8  # admin login attempts per minute per IP


async def limit_login(request: Request) -> None:
    """Brute-force guard for the admin token."""
    q, now = LOGIN_HITS[request.client.host if request.client else "?"], time.monotonic()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= LOGIN_RATE:
        raise HTTPException(429, "Too many attempts. Please wait a minute.")
    q.append(now)
