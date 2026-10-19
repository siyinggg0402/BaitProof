"""Cross-cutting web concerns: anonymous per-visitor profiles, rate limiting, security headers."""
from __future__ import annotations

import os
import secrets
import time
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Request

from core.storage import db


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
        return resp
