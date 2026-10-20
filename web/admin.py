"""Operator dashboard. Disabled unless BAITPROOF_ADMIN_TOKEN is set. Shows health, spend and gate behaviour from the event log;
the log contains no message text, so neither does this page."""
from __future__ import annotations

import hashlib
import hmac
import os
import time

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from core.obs import health, read_events, recent_checks, summarize
from web.deps import limit_login

router = APIRouter(prefix="/admin")
HOURS = {1: "1 hour", 24: "24 hours", 168: "7 days"}


def _token() -> str:
    return os.getenv("BAITPROOF_ADMIN_TOKEN", "")


def _cookie() -> str:
    return hmac.new(b"bp-admin-session", _token().encode(), hashlib.sha256).hexdigest()  # never the token itself


def _authed(request: Request) -> bool:
    tok = _token()
    if not tok:
        return False
    header = request.headers.get("x-admin-token", "")
    return hmac.compare_digest(header, tok) or hmac.compare_digest(request.cookies.get("bp_admin", ""), _cookie())


def enabled() -> None:
    if not _token():
        raise HTTPException(404)  # indistinguishable from a route that doesn't exist


def _data(hours: int) -> dict:
    events = read_events(since=time.time() - hours * 3600)
    return {"health": health(events), "summary": summarize(events), "recent": recent_checks(events), "hours": hours}


def _hours(h: int) -> int:
    return h if h in HOURS else 24


NOCACHE = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex"}


def mount(templates: Jinja2Templates) -> APIRouter:
    @router.get("/login", response_class=HTMLResponse, dependencies=[Depends(enabled)])
    def login_page(request: Request):
        return templates.TemplateResponse(request, "admin_login.html", {"error": "", "ai": True, "map": None}, headers=NOCACHE)

    @router.post("/login", dependencies=[Depends(enabled), Depends(limit_login)])
    def login(request: Request, token: str = Form("")):
        if not hmac.compare_digest(token, _token()):
            return templates.TemplateResponse(request, "admin_login.html", {"error": "That token isn't right.", "ai": True, "map": None}, status_code=401, headers=NOCACHE)
        r = RedirectResponse("/admin", status_code=303)
        r.set_cookie("bp_admin", _cookie(), httponly=True, samesite="strict", secure=request.url.scheme == "https", max_age=8 * 3600, path="/admin")
        return r

    @router.post("/logout", dependencies=[Depends(enabled)])
    def logout():
        r = RedirectResponse("/admin/login", status_code=303)
        r.delete_cookie("bp_admin", path="/admin")
        return r

    @router.get("", response_class=HTMLResponse, dependencies=[Depends(enabled)])
    def dashboard(request: Request, hours: int = 24):
        if not _authed(request):
            return RedirectResponse("/admin/login", status_code=303)
        return templates.TemplateResponse(request, "admin.html", {**_data(_hours(hours)), "windows": HOURS, "ai": True, "map": None}, headers=NOCACHE)

    @router.get("/metrics.json", dependencies=[Depends(enabled)])
    def metrics(request: Request, hours: int = 24):
        if not _authed(request):
            raise HTTPException(401, "admin token required")
        return JSONResponse(_data(_hours(hours)), headers=NOCACHE)

    return router
