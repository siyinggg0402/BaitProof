"""Scam Road: the page and its API. The browser drives; the server deals the messages, grades each lane the car takes and adds up the distance."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from core.game import garage, looks, road
from core.storage import accounts, links, runs
from web.deps import limit_expensive, request_lang
from web.pages import page

router = APIRouter()


class StartIn(BaseModel):
    mode: str = "road"


class GarageIn(BaseModel):
    car: str
    hat: str


class AnswerIn(BaseModel):
    run: str
    gate: str
    lane: int


class FinishIn(BaseModel):
    run: str


def _run(run_id: str) -> road.Run:
    try:
        return road.get(run_id, links.current_profile())
    except road.RoadError as e:
        raise HTTPException(404, str(e))


@router.get("/road", response_class=HTMLResponse)
def road_page(request: Request):
    me = links.current_profile()
    return page(request, "road.html", best=runs.best(me), friends_n=len(accounts.friends(me)), look=looks.character(me))


@router.post("/api/road/start", dependencies=[Depends(limit_expensive)])
def start(request: Request, body: StartIn | None = None):
    try:
        return road.start(links.current_profile(), request_lang(request), mode=(body.mode if body else "road"))
    except road.RoadError as e:
        raise HTTPException(400, str(e))


@router.get("/api/road/garage")
def garage_catalog(request: Request):
    return garage.catalog(links.current_profile(), request_lang(request))


@router.post("/api/road/garage")
def garage_choose(request: Request, body: GarageIn):
    try:
        garage.choose(links.current_profile(), body.car, body.hat)
    except garage.GarageError as e:
        raise HTTPException(400, str(e))
    return garage.catalog(links.current_profile(), request_lang(request))


@router.post("/api/road/answer")
def answer(request: Request, body: AnswerIn):
    try:
        return road.answer(_run(body.run), body.gate, body.lane, request_lang(request))
    except road.RoadError as e:
        raise HTTPException(400, str(e))


@router.post("/api/road/finish")
def finish(request: Request, body: FinishIn):
    return road.finish(_run(body.run), request_lang(request))
