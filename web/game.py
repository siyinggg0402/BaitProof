"""Game API + page. All progress lives in the visitor's own profile; answers stay on the server until revealed."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from core.game import engine
from core.storage import links
from web.deps import limit_expensive

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
    def state():
        return engine.overview()

    @router.post("/api/game/start", dependencies=[Depends(limit_expensive)])
    def start(body: StartIn):
        try:
            return engine.public(engine.start(body.mode, body.trick, owner=links.current_profile()))
        except engine.GameError as e:
            raise HTTPException(400, str(e))

    @router.post("/api/game/answer")
    def answer(body: AnswerIn):
        try:
            return engine.answer(_round(body.round), body.item_id, body.choice, body.picked, body.fast)
        except engine.GameError as e:
            raise HTTPException(400, str(e))

    @router.post("/api/game/finish")
    def finish(body: FinishIn):
        return engine.finish(_round(body.round))

    return router
