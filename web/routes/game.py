"""Game API + page. All progress lives in the visitor's own profile; answers stay on the server until revealed."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from core.game import engine
from core.storage import links
from web.deps import limit_expensive, request_lang

router = APIRouter()


class StartIn(BaseModel):
    mode: str
    trick: str = ""


class AnswerIn(BaseModel):
    round: str
    item_id: str
    choice: str | None = None
    picked: list[int] | None = None
    fast: bool = False


class FinishIn(BaseModel):
    round: str


def _round(rid: str) -> engine.Round:
    try:
        return engine.get(rid, links.current_profile())
    except engine.GameError as e:
        raise HTTPException(404, str(e))


def mount(page) -> APIRouter:
    @router.get("/game", response_class=HTMLResponse)
    def game_page(request: Request):
        return page(request, "game.html")

    @router.get("/api/game/state")
    def state(request: Request):
        return engine.overview(request_lang(request))

    @router.post("/api/game/start", dependencies=[Depends(limit_expensive)])
    def start(request: Request, body: StartIn):
        lang = request_lang(request)
        try:
            return engine.public(engine.start(body.mode, body.trick, owner=links.current_profile(), lang=lang), lang)
        except engine.GameError as e:
            raise HTTPException(400, str(e))

    @router.post("/api/game/answer")
    def answer(request: Request, body: AnswerIn):
        try:
            return engine.answer(_round(body.round), body.item_id, body.choice, body.picked, body.fast, request_lang(request))
        except engine.GameError as e:
            raise HTTPException(400, str(e))

    @router.post("/api/game/finish")
    def finish(request: Request, body: FinishIn):
        return engine.finish(_round(body.round), request_lang(request))

    return router
