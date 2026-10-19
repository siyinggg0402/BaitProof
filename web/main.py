from __future__ import annotations

import os
import secrets
import time
from collections import OrderedDict, defaultdict, deque
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import core  # noqa: F401  (loads .env)
from core.ai import llm
from core.domain.schemas import Drill
from core.domain.tactics import TACTICS
from core.pipelines import challenge, check, train
from core.storage import db, model
from web import cardimg

BASE = Path(__file__).parent

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


app = FastAPI(title="Baitproof", dependencies=[Depends(bind_profile)])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    if pid := getattr(request.state, "new_profile", None):
        resp.set_cookie("bp", pid, max_age=31536000, httponly=True, samesite="lax", secure=request.url.scheme == "https")
    resp.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "same-origin"
    return resp

app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")

SESSIONS: "OrderedDict[str, dict[str, Drill]]" = OrderedDict()  # in-memory; answers never leave the server


def page(request: Request, name: str, **ctx):
    return templates.TemplateResponse(request, name, {"map": model.resilience_map(), "ai": llm.available(), "labels": {k: v["label"] for k, v in TACTICS.items()}, **ctx})


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return page(request, "index.html", result=None, text="")


@app.post("/check", response_class=HTMLResponse, dependencies=[Depends(limit_expensive)])
def do_check(request: Request, message: str = Form(...)):
    if not message.strip():
        raise HTTPException(400, "Paste a message to check.")
    result = check.check_message(message)
    return page(request, "index.html", result=result, text=message[:4000])


@app.get("/train", response_class=HTMLResponse)
def train_page(request: Request):
    return page(request, "train.html")


class StartOut(BaseModel):
    session: str
    items: list[dict]
    map: dict


@app.post("/api/train/start", dependencies=[Depends(limit_expensive)])
def train_start():
    drills = train.build_session()
    sid = drills[0].id + "s" if drills else "empty"
    SESSIONS[sid] = {d.id: d for d in drills}
    while len(SESSIONS) > 200:
        SESSIONS.popitem(last=False)
    return {"session": sid, "items": [d.public() for d in drills], "map": model.resilience_map()}


class AnswerIn(BaseModel):
    session: str
    item_id: str
    choice: int | None = None
    text: str = ""


@app.post("/api/train/answer")
def train_answer(a: AnswerIn):
    drill = SESSIONS.get(a.session, {}).get(a.item_id)
    if not drill:
        raise HTTPException(404, "That practice session expired. Start a new one.")
    before = model.baitproof_score()
    g = train.grade(drill, a.choice, a.text)
    m = model.resilience_map()
    return {"result": g.result, "note": g.note, "correct_index": drill.correct_index, "map": m, "delta": m["score"] - before}


@app.post("/challenge/new", dependencies=[Depends(limit_expensive)])
def challenge_new():
    return RedirectResponse(f"/challenge/{challenge.create()}", status_code=303)


@app.get("/challenge/{cid}", response_class=HTMLResponse)
def challenge_page(request: Request, cid: str):
    items = challenge.get(cid)
    if items is None:
        raise HTTPException(404, "Challenge not found")
    return page(request, "challenge.html", cid=cid, items=[{"text": i["text"]} for i in items])


class SubmitIn(BaseModel):
    answers: list[bool | None]


@app.post("/api/challenge/{cid}/submit")
def challenge_submit(cid: str, body: SubmitIn):
    items = challenge.get(cid)
    if items is None:
        raise HTTPException(404, "Challenge not found")
    res = challenge.score(items, body.answers)
    res["card_url"] = f"/card/{cid}?s={res['right']}"
    return res


@app.get("/card/{cid}", response_class=HTMLResponse)
def card(request: Request, cid: str, s: int = 0):
    items = challenge.get(cid)
    if items is None:
        raise HTTPException(404, "Challenge not found")
    total = len(items)
    s = max(0, min(s, total))
    return page(request, "card.html", cid=cid, pct=round(100 * s / total), right=s, total=total,
                url=str(request.url_for("challenge_page", cid=cid)),
                image=str(request.url_for("card_image", cid=cid)) + f"?s={s}")


@app.get("/card-image/{cid}.png")
def card_image(cid: str, s: int = 0):
    """Share-card image for link previews (Open Graph). Public: contains only the score, no message content."""
    items = challenge.get(cid)
    if items is None:
        raise HTTPException(404, "Challenge not found")
    s = max(0, min(s, len(items)))
    return Response(cardimg.render(round(100 * s / len(items)), s, len(items)), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/map")
def api_map():
    return model.resilience_map()
