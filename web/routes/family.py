"""Family groups: start one, invite with a code or link, share the scams you met so they become gates in each other's games, and a leaderboard just for the family.
What is shared is only the redacted example the library keeps, and the page shows exactly that. Other people only ever see cards (nickname, avatar, public id)."""
from __future__ import annotations

import os

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core.storage import accounts, dashboard, groups, library, links, model, push, runs
from core.storage.accounts import AccountError
from core.storage.groups import GroupError
from web.deps import request_lang
from web.pages import page
from web.routes.account import BOARDS, NO_STORE
from web.ui import tr

router = APIRouter()


def _me() -> str:
    return links.current_profile()


def _invite(request: Request, code: str) -> str:
    base = os.getenv("BAITPROOF_URL", "").rstrip("/") or str(request.base_url).rstrip("/")
    return f"{base}/family/join/{code}"


def _view(request: Request, name: str = "family.html", status_code: int = 200, **ctx):
    me = _me()
    group = groups.of(me)
    ctx.setdefault("error", "")
    ctx.setdefault("game", "road")
    ctx.setdefault("scope", "week")
    resp = page(request, name, group=group, invite=_invite(request, group["code"]) if group else "", account=accounts.get(me), avatars=accounts.AVATARS, **ctx)
    resp.status_code = status_code
    resp.headers.update(NO_STORE)
    return resp


def _err(request: Request, e: Exception) -> str:
    return tr(str(e), request_lang(request))


@router.get("/family", response_class=HTMLResponse)
def family_page(request: Request, game: str = "road", scope: str = "", shared: str = ""):
    me = _me()
    game = game if game in BOARDS else "road"
    scope = scope if scope in BOARDS[game] else BOARDS[game][0]
    group = groups.of(me)
    mine = []
    if group:
        have = {s["text"] for s in group["scams"]}
        mine = [e for e in library.user_examples()[:8] if e["text"] not in have]
    board = runs.group_board(me, groups.member_profiles(me), scope, game) if group else []
    return _view(request, game=game, scope=scope, scopes=BOARDS[game], board=board, mine=mine, shared=bool(shared))


def _failed(request: Request, e: Exception):
    return _view(request, status_code=400, error=_err(request, e), scopes=BOARDS["road"], board=[], mine=[], shared=False)


def _consent(share: str, asked: str) -> bool:
    """The "share my progress" tick box: on when ticked; on by default for a caller that did not show the box at all."""
    return share == "yes" if asked else True


@router.post("/family/create")
def create(request: Request, name: str = Form(""), share: str = Form(""), consent_asked: str = Form("")):
    try:
        groups.create(_me(), name, _consent(share, consent_asked))
    except GroupError as e:
        return _failed(request, e)
    return RedirectResponse("/family", 303)


@router.post("/family/leave")
def leave():
    groups.leave(_me())
    return RedirectResponse("/family", 303)


@router.post("/family/delete")
def delete(request: Request, confirm: str = Form("")):
    if confirm == "yes":
        try:
            groups.delete(_me())
        except GroupError as e:
            return _failed(request, e)
    return RedirectResponse("/family", 303)


@router.post("/family/remove")
def remove(pub: str = Form("")):
    try:
        groups.remove_member(_me(), pub)
    except GroupError:
        pass
    return RedirectResponse("/family", 303)


@router.post("/family/code")
def new_code():
    try:
        groups.new_code(_me())
    except GroupError:
        pass
    return RedirectResponse("/family", 303)


@router.post("/family/share")
def share(request: Request, ex: str = Form("latest")):
    try:
        groups.share(_me(), ex)
    except GroupError as e:
        return _failed(request, e)
    return RedirectResponse("/family?shared=1", 303)


@router.post("/family/unshare")
def unshare(scam: int = Form(0)):
    groups.unshare(_me(), scam)
    return RedirectResponse("/family", 303)


# ---------------------------------------------------------------- invites
@router.get("/family/join/{code}", response_class=HTMLResponse)
def join_page(request: Request, code: str):
    card = groups.by_code(code)
    if card is not None and groups.of(_me()):
        return RedirectResponse("/family", 303)
    return _view(request, "family_join.html", 200 if card else 404, card=card, code=code.upper())


@router.post("/family/join/{code}", response_class=HTMLResponse)
def join(request: Request, code: str, nickname: str = Form(""), avatar: str = Form(""), share: str = Form(""), consent_asked: str = Form("")):
    card = groups.by_code(code)
    if card is None:
        return _view(request, "family_join.html", 404, card=None, code=code.upper())
    me = _me()
    key = ""
    if accounts.get(me) is None:
        try:
            _, key = accounts.create(me, nickname, avatar)
        except AccountError as e:
            return _view(request, "family_join.html", 400, card=card, code=code.upper(), error=_err(request, e), nickname=nickname)
    try:
        groups.join(me, code, _consent(share, consent_asked))
    except GroupError as e:
        return _view(request, "family_join.html", 400, card=card, code=code.upper(), error=_err(request, e))
    if key:  # a new profile was made on the way in: show its sign-in key once, like everywhere else
        from web.routes.account import _view as account_view

        return account_view(request, "me.html", new_key=key, error="", join="", joined=card["name"])
    return RedirectResponse("/family", 303)


# ---------------------------------------------------------------- the dashboard
@router.get("/family/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request, nudged: str = ""):
    me = _me()
    lang = request_lang(request)
    fam = dashboard.family(me, lang)
    if fam is None:
        return RedirectResponse("/family", 303)
    levels = {k: (model.LEVEL_TEXT[k] if lang == "en" else tr(model.LEVEL_KEYS[k], lang)) for k in model.LEVEL_TEXT}
    return _view(request, "family_dashboard.html", fam=fam, levels=levels, summary_text=dashboard.summary_text(fam, lang), nudged=nudged if nudged in ("sent", "nopush", "limit") else "")


@router.post("/family/share-progress")
def share_progress(on: str = Form("")):
    groups.set_share(_me(), on == "yes")
    return RedirectResponse("/family/dashboard", 303)


@router.post("/family/nudge")
def nudge(pub: str = Form("")):
    me = _me()
    target = next((m for m in groups.members_for_dashboard(me) if m["pub"] == pub and not m["you"] and m["shares"]), None)
    result = push.notify_nudge(me, target["profile"]) if target else "nopush"
    return RedirectResponse(f"/family/dashboard?nudged={result}", 303)
