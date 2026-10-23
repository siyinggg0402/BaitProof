"""Your profile, signing in on another device, friends, and invite links. No emails and no passwords: a profile gets a nickname, an avatar, a code friends
use to find it, and a sign-in key shown once. Other people only ever see a nickname, an avatar and a public id: never the profile id, which is the cookie."""
from __future__ import annotations

import os
import secrets
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from core.storage import accounts, db, links, push, runs
from core.storage.accounts import AccountError
from web.deps import limit_login, set_profile_cookie
from web.pages import page
from web.ui import tr
from web.deps import request_lang

router = APIRouter()
NO_STORE = {"Cache-Control": "no-store"}  # a page that shows a sign-in key is never kept by the browser or a proxy


def _me() -> str:
    return links.current_profile()


def _invite_url(request: Request, code: str) -> str:
    base = os.getenv("BAITPROOF_URL", "").rstrip("/") or str(request.base_url).rstrip("/")
    return f"{base}/join/{code}"


def _view(request: Request, name: str, status_code: int = 200, **ctx):
    acct = accounts.get(_me())
    resp = page(request, name, avatars=accounts.AVATARS, invite=_invite_url(request, acct["friend_code"]) if acct else "", **ctx)
    resp.status_code = status_code
    resp.headers.update(NO_STORE)
    return resp


def _error(request: Request, e: AccountError) -> str:
    return tr(str(e), request_lang(request))


# ---------------------------------------------------------------- profile
@router.get("/me", response_class=HTMLResponse)
def me_page(request: Request):
    return _view(request, "me.html", new_key="", error="", join="")


@router.post("/me/create", response_class=HTMLResponse)
def me_create(request: Request, nickname: str = Form(""), avatar: str = Form(""), join: str = Form("")):
    try:
        _, key = accounts.create(_me(), nickname, avatar)
    except AccountError as e:
        return _view(request, "me.html", 400, new_key="", error=_error(request, e), join=join, nickname=nickname)
    joined = ""
    if join:
        try:
            joined = accounts.add_friend(_me(), join)["nickname"]
        except AccountError:
            joined = ""  # the profile is made either way; a stale invite is not worth failing for
    return _view(request, "me.html", new_key=key, error="", join="", joined=joined)


@router.post("/me/update")
def me_update(request: Request, nickname: str = Form(""), avatar: str = Form("")):
    try:
        accounts.update(_me(), nickname or None, avatar or None)
    except AccountError as e:
        return _view(request, "me.html", 400, new_key="", error=_error(request, e), join="")
    return RedirectResponse("/me", 303)


@router.post("/me/key", response_class=HTMLResponse)
def me_new_key(request: Request):
    try:
        key = accounts.new_key(_me())
    except AccountError as e:
        return _view(request, "me.html", 400, new_key="", error=_error(request, e), join="")
    return _view(request, "me.html", new_key=key, error="", join="")


@router.post("/me/code")
def me_new_code(request: Request):
    try:
        accounts.new_friend_code(_me())
    except AccountError:
        pass
    return RedirectResponse("/me", 303)


@router.post("/me/delete")
def me_delete(confirm: str = Form("")):
    if confirm == "yes":
        accounts.delete(_me())
    return RedirectResponse("/me" if confirm != "yes" else "/", 303)


# ---------------------------------------------------------------- signing in and out
@router.get("/signin", response_class=HTMLResponse)
def signin_page(request: Request):
    return _view(request, "signin.html", error="")


@router.post("/signin", response_class=HTMLResponse, dependencies=[Depends(limit_login)])
def signin(request: Request, key: str = Form("")):
    pid = accounts.sign_in(key)
    if pid is None:
        return _view(request, "signin.html", 400, error=tr("That key doesn't match a profile. Check it and try again.", request_lang(request)))
    resp = RedirectResponse("/me", 303)
    if db.multiuser():
        set_profile_cookie(resp, request, pid)
    return resp


@router.post("/signout")
def signout(request: Request):
    resp = RedirectResponse("/", 303)
    if db.multiuser():
        set_profile_cookie(resp, request, secrets.token_hex(16))  # this browser starts a new, empty profile; the account is still there for its key
    return resp


# ---------------------------------------------------------------- invites and friends
@router.get("/join/{code}", response_class=HTMLResponse)
def join_page(request: Request, code: str):
    card = accounts.invite_card(code)
    mine = accounts.get(_me())
    if card is not None and mine is not None and card["pub"] == mine["pub"]:
        return RedirectResponse("/friends", 303)
    return _view(request, "join.html", 200 if card else 404, card=card, code=code.upper(), error="")


@router.post("/join/{code}", response_class=HTMLResponse)
def join(request: Request, code: str, nickname: str = Form(""), avatar: str = Form("")):
    card = accounts.invite_card(code)
    if card is None:
        return _view(request, "join.html", 404, card=None, code=code.upper(), error="")
    if accounts.get(_me()) is None:
        try:
            _, key = accounts.create(_me(), nickname, avatar)
        except AccountError as e:
            return _view(request, "join.html", 400, card=card, code=code.upper(), error=_error(request, e), nickname=nickname)
        try:
            accounts.add_friend(_me(), code)
        except AccountError:
            pass
        return _view(request, "me.html", new_key=key, error="", join="", joined=card["nickname"])
    try:
        accounts.add_friend(_me(), code)
    except AccountError as e:
        return _view(request, "join.html", 400, card=card, code=code.upper(), error=_error(request, e))
    return RedirectResponse(f"/friends?added={quote(card['nickname'])}", 303)


BOARDS = {"road": ("week", "all"), "daily": ("day",), "link": ("week", "all")}   # each game and the time ranges its board offers


def _board_view(request: Request, me: str, game: str, scope: str, **ctx):
    game = game if game in BOARDS else "road"
    scope = scope if scope in BOARDS[game] else BOARDS[game][0]
    acct = accounts.get(me)
    return _view(request, "friends.html", game=game, scope=scope, scopes=BOARDS[game], push_on=bool(acct) and push.enabled(), friends=accounts.friends(me) if acct else [],
                 board=runs.board(me, scope, game) if acct else [], best=runs.best(me), **ctx)


@router.get("/friends", response_class=HTMLResponse)
def friends_page(request: Request, game: str = "road", scope: str = "", added: str = ""):
    added = added if accounts._NAME_OK.fullmatch(added) and len(added) <= accounts.NAME_MAX else ""    # (only a name that could be a nickname: a made-up link cannot put its own words on the page)
    return _board_view(request, _me(), game, scope, added=added, error="")


@router.post("/friends/add", response_class=HTMLResponse)
def friends_add(request: Request, code: str = Form("")):
    try:
        card = accounts.add_friend(_me(), code)
    except AccountError as e:
        view = _board_view(request, _me(), "road", "week", added="", error=_error(request, e))
        view.status_code = 400
        return view
    return RedirectResponse(f"/friends?added={quote(card['nickname'])}", 303)


@router.post("/friends/remove")
def friends_remove(pub: str = Form("")):
    accounts.remove_friend(_me(), pub)
    return RedirectResponse("/friends", 303)
