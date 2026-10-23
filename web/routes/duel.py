"""Live head-to-head races: the hub (challenge a friend, your open races, invitations), the race page (the 3D road in race mode) and the small API the page polls.
Everything about a race is checked on the server: who may see it, who may start it, and every answer (through the ordinary Scam Road API)."""
from __future__ import annotations

import os
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core.game import duel
from core.storage import accounts, links, push
from web.deps import limit_expensive, request_lang
from web.ui import tr
from web.pages import page

router = APIRouter()


def _me() -> str:
    return links.current_profile()


def _invite(request: Request, code: str) -> str:
    base = os.getenv("BAITPROOF_URL", "").rstrip("/") or str(request.base_url).rstrip("/")
    return f"{base}/duel/{code}"


def _fail(e: duel.DuelError, status: int = 400):
    raise HTTPException(404 if "isn't open" in str(e) else 403 if "not in that race" in str(e) else status, str(e))


# ---------------------------------------------------------------- pages
GONE = "That race isn't open any more."
SAYS = {GONE, "You already have three races open. Finish or leave one first.", "Not enough messages for a race yet.", "That race has already started.", "That race is full.",
        "Make a profile first to race."}   # (the hub page only ever shows one of our own messages: a made-up ?error= link cannot put its own words on the page)


@router.get("/duel", response_class=HTMLResponse)
def hub(request: Request, error: str = ""):
    me = _me()
    error = tr(error, request_lang(request)) if error in SAYS else ""
    acct = accounts.get(me)
    friends = accounts.friends(me) if acct else []
    records = {f["pub"]: duel.record(me, p) for f in friends for p in [_profile_of(me, f["pub"])] if p}
    return page(request, "duel_hub.html", friends=friends, records=records, invites=duel.invites_for(me), mine=duel.mine(me), error=error)


def _profile_of(me: str, pub: str) -> str:
    """INTERNAL: a friend's profile id from their public id (to read the head-to-head record). Never sent to a browser."""
    from core.storage import db

    with db.connect(shared=True) as c:
        r = c.execute("SELECT a.profile FROM friendships f JOIN accounts a ON a.profile=f.b WHERE f.a=? AND a.pub=?", (me, pub)).fetchone()
    return r["profile"] if r else ""


@router.post("/duel/new", dependencies=[Depends(limit_expensive)])
def new(request: Request, pub: list[str] = Form(default=[])):
    me = _me()
    try:
        d = duel.create(me, request_lang(request), pub)
    except duel.DuelError as e:
        return RedirectResponse(f"/duel?error={quote(str(e))}", 303)
    push.notify_challenge(me, duel.invited_profiles(d, me), d.code)
    return RedirectResponse(f"/duel/{d.code}", 303)


@router.get("/duel/{code}", response_class=HTMLResponse)
def race_page(request: Request, code: str):
    me = _me()
    try:
        d = duel._get(code, allow_closed=True)
    except duel.DuelError:
        return RedirectResponse(f"/duel?error={quote(GONE)}", 303)
    return page(request, "road.html", best=0, friends_n=len(accounts.friends(me)), duel_code=d.code, invite=_invite(request, d.code))


# ---------------------------------------------------------------- the API the race page polls
@router.get("/api/duel/{code}")
def poll(request: Request, code: str, run: int = 0):
    try:
        return duel.view_by_code(code, _me(), bool(run), request_lang(request))
    except duel.DuelError as e:
        _fail(e)


@router.post("/api/duel/{code}/join", dependencies=[Depends(limit_expensive)])
def join(request: Request, code: str):
    me = _me()
    try:
        d = duel.join(code, me, request_lang(request))
        return duel.view(d, me, lang=request_lang(request))
    except duel.DuelError as e:
        _fail(e)


@router.post("/api/duel/{code}/start", dependencies=[Depends(limit_expensive)])
def start(request: Request, code: str):
    me = _me()
    try:
        return duel.view(duel.start(code, me), me, with_run=True, lang=request_lang(request))
    except duel.DuelError as e:
        _fail(e)


@router.post("/api/duel/{code}/leave")
def leave(code: str):
    duel.leave(code, _me())
    return {"left": True}


@router.post("/api/duel/{code}/rematch", dependencies=[Depends(limit_expensive)])
def rematch(request: Request, code: str):
    """Open a new lobby with the same drivers asked in (only the ones who are this person's friends can be asked; others get the link)."""
    me = _me()
    try:
        old = duel._get(code, allow_closed=True)
        if next((p for p in old.players if p.profile == me), None) is None:
            raise duel.DuelError("You are not in that race.")
        d = duel.create(me, request_lang(request), [p.pub for p in old.players if p.profile != me])
    except duel.DuelError as e:
        _fail(e)
    push.notify_challenge(me, duel.invited_profiles(d, me), d.code)
    return {"code": d.code}
