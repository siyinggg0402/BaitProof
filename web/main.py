from __future__ import annotations

from collections import OrderedDict
from contextlib import asynccontextmanager
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
from core.storage import model
from web import cardimg
from web.deps import add_security_headers, bind_profile, limit_expensive

BASE = Path(__file__).parent

@asynccontextmanager
async def lifespan(_app: FastAPI):
    llm.warmup()  # avoid the model's cold start landing on the first visitor
    yield


app = FastAPI(title="Baitproof", dependencies=[Depends(bind_profile)], lifespan=lifespan)
add_security_headers(app)

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
