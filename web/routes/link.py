"""Link Hunt: the page and its API. The server makes the questions, keeps the answer, grades each pick and adds up the score."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from core.game import linkhunt
from core.storage import accounts, links, runs
from web.deps import limit_expensive, request_lang
from web.pages import page

router = APIRouter()


class PickIn(BaseModel):
    hunt: str
    question: str
    choice: int


class FinishIn(BaseModel):
    hunt: str


def _hunt(hunt_id: str) -> linkhunt.Hunt:
    try:
        return linkhunt.get(hunt_id, links.current_profile())
    except linkhunt.LinkError as e:
        raise HTTPException(404, str(e))


@router.get("/link", response_class=HTMLResponse)
def link_page(request: Request):
    me = links.current_profile()
    return page(request, "link.html", best=runs.best(me, runs.LINK), friends_n=len(accounts.friends(me)))


@router.post("/api/link/start", dependencies=[Depends(limit_expensive)])
def start(request: Request):
    return linkhunt.start(links.current_profile(), request_lang(request))


@router.post("/api/link/answer")
def answer(request: Request, body: PickIn):
    try:
        return linkhunt.answer(_hunt(body.hunt), body.question, body.choice, request_lang(request))
    except linkhunt.LinkError as e:
        raise HTTPException(400, str(e))


@router.post("/api/link/finish")
def finish(request: Request, body: FinishIn):
    return linkhunt.finish(_hunt(body.hunt), request_lang(request))
