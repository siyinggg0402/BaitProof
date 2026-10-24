"""The house: your room (buy things with your points, move them around) and a friend's, to look at. The browser draws the 3D room; the server owns the rules: what you own,
what it costs, what fits where (core/game/house.py). A friend's house shows only the layout and the look of the room, never their points or what is in their cupboard."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from core.game import house, looks
from core.storage import accounts, db, links
from web.deps import request_lang
from web.pages import page
from web.ui import tr

router = APIRouter()
NO_STORE = {"Cache-Control": "no-store"}


def _json(data: dict) -> JSONResponse:
    return JSONResponse(data, headers=NO_STORE)


class BuyIn(BaseModel):
    item: str


class StyleIn(BaseModel):
    part: str
    style: str


class LayoutIn(BaseModel):
    layout: list[dict] = Field(max_length=house.MAX_PLACED)


class LookIn(BaseModel):
    look: str


def _fail(request: Request, e: Exception) -> HTTPException:
    return HTTPException(400, tr(str(e), request_lang(request)))


def _mine(request: Request) -> dict:
    me = links.current_profile()
    acct = accounts.get(me)
    return {**house.view(request_lang(request)), "look": looks.character(me), "has_character": looks.has_character(me), "nickname": acct["nickname"] if acct else "", "visit": False}


@router.get("/house", response_class=HTMLResponse)
def house_page(request: Request):
    resp = page(request, "house.html", visit_pub="", visit_name="")
    resp.headers.update(NO_STORE)
    return resp


@router.get("/api/house")
def house_view(request: Request):
    return _json(_mine(request))


@router.post("/api/house/buy")
def house_buy(request: Request, body: BuyIn):
    try:
        house.buy(body.item)
    except house.HouseError as e:
        raise _fail(request, e)
    return _json(_mine(request))


@router.post("/api/house/style")
def house_style(request: Request, body: StyleIn):
    try:
        house.buy_style(body.part, body.style)
    except house.HouseError as e:
        raise _fail(request, e)
    return _json(_mine(request))


@router.post("/api/house/layout")
def house_layout(request: Request, body: LayoutIn):
    try:
        house.save_layout(body.layout)
    except house.HouseError as e:
        raise _fail(request, e)
    return _json(_mine(request))


@router.post("/api/house/look")
def house_look(request: Request, body: LookIn):
    try:
        looks.set_character(links.current_profile(), body.look)
    except looks.LookError as e:
        raise _fail(request, e)
    return _json(_mine(request))


def _visit(request: Request, pub: str) -> dict:
    target = accounts.visit_target(links.current_profile(), pub)
    if target is None:
        raise HTTPException(404, tr("That house isn't open to you. Houses are open to friends.", request_lang(request)))
    profile, card = target
    with db.as_profile(profile):                       # (their own database, read for a moment)
        view = house.public_view(request_lang(request))
        look = looks.character(profile)
    return {**view, "look": look, "nickname": card["nickname"], "avatar": card["avatar"], "visit": True}


@router.get("/house/visit/{pub}", response_class=HTMLResponse)
def visit_page(request: Request, pub: str):
    data = _visit(request, pub)
    resp = page(request, "house.html", visit_pub=pub, visit_name=data["nickname"])
    resp.headers.update(NO_STORE)
    return resp


@router.get("/api/house/visit/{pub}")
def visit_view(request: Request, pub: str):
    return _json(_visit(request, pub))
