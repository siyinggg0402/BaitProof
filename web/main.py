from __future__ import annotations

import asyncio
import contextvars
import json
import os
import queue
import re
import threading
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

import core  # noqa: F401  (loads .env)
from core.ai import llm
from core import obs
from core.domain.schemas import Drill
from core.domain.tactics import TACTICS
from core.pipelines import challenge, check, train
from core.storage import history, links, model
from web import cardimg
from web import admin, game, results
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
templates.env.globals["STAGES"] = {  # plain-language names for the pipeline's stages
    "ingest": "Read the message", "triage": "Checked how you're doing", "intent": "Worked out what it asks of you", "tools": "Checked links and numbers",
    "analysis": "AI review", "grounding": "Verified claims against the message", "arbiter": "Weighed the evidence", "loop": "Investigated further",
    "second-look": "Took a second look", "sufficiency": "Confidence check", "critic": "Second reviewer", "output": "Final safety checks",
    "flywheel": "Added to your practice", "guard": "Safety net"}
templates.env.filters["timestamp"] = lambda t: __import__("time").strftime("%H:%M:%S", __import__("time").localtime(t))
app.include_router(admin.mount(templates))

SESSIONS: "OrderedDict[str, dict[str, Drill]]" = OrderedDict()  # in-memory; answers never leave the server


def page(request: Request, name: str, **ctx):
    return templates.TemplateResponse(request, name, {"map": model.resilience_map(), "ai": llm.available(), "labels": {k: v["label"] for k, v in TACTICS.items()}, **ctx})


app.include_router(game.mount(page))


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return page(request, "index.html", result=None, text="")


@app.post("/check", response_class=HTMLResponse, dependencies=[Depends(limit_expensive)])
def do_check(request: Request, message: str = Form(...)):
    if not message.strip():
        raise HTTPException(400, "Paste a message to check.")
    result = check.check_message(message)
    history.add(result, "web", message)
    return page(request, "index.html", result=result, text=message[:4000])


class StreamIn(BaseModel):
    message: str


@app.post("/api/check/stream", dependencies=[Depends(limit_expensive)])
async def check_stream(body: StreamIn):
    """Live view: Server-Sent Events, one per gate as it runs, then 'done' with the id of the finished check."""
    text = body.message.strip()
    if not text:
        raise HTTPException(400, "Paste a message to check.")
    q: "queue.Queue[tuple[str, object]]" = queue.Queue()
    ctx = contextvars.copy_context()  # carries the visitor's profile into the worker thread

    def work() -> None:
        try:
            r = ctx.run(check.check_message, text, True, lambda step: q.put(("step", step.model_dump())))
            ctx.run(results.put, r)
            ctx.run(history.add, r, "web", text)
            q.put(("done", r.check_id))
        except Exception as e:
            q.put(("error", type(e).__name__))

    threading.Thread(target=work, daemon=True).start()

    async def events():
        loop = asyncio.get_running_loop()
        while True:
            try:
                kind, payload = await loop.run_in_executor(None, lambda: q.get(timeout=60))
            except queue.Empty:
                kind, payload = "error", "timeout"
            yield f"data: {json.dumps({'type': kind, 'data': payload})}\n\n"
            if kind in ("done", "error"):
                return

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/result/{check_id}", response_class=HTMLResponse)
def result_partial(request: Request, check_id: str):
    r = results.get(check_id)
    if r is None:
        raise HTTPException(404, "That result has expired. Please check the message again.")
    return templates.TemplateResponse(request, "_result.html", {"result": r, "labels": {k: v["label"] for k, v in TACTICS.items()}})


class FeedbackIn(BaseModel):
    check_id: str
    rating: str


FEEDBACK_SEEN: set[tuple[str, str]] = set()


@app.post("/api/feedback")
def feedback(request: Request, body: FeedbackIn):
    """Thumbs up/down on a verdict. Stores only the check id and the rating, never the message."""
    if body.rating not in ("up", "down") or not re.fullmatch(r"[0-9a-f]{12}", body.check_id):
        raise HTTPException(422, "invalid feedback")
    key = (request.client.host if request.client else "?", body.check_id)
    if key not in FEEDBACK_SEEN:
        if len(FEEDBACK_SEEN) > 5000:
            FEEDBACK_SEEN.clear()
        FEEDBACK_SEEN.add(key)
        obs.emit({"kind": "feedback", "check_id": body.check_id, "rating": body.rating})
    return {"ok": True}


# ---------------------------------------------------------------- records + Telegram link
def _ago(ts: str) -> str:
    from datetime import datetime, timezone

    secs = int((datetime.now(timezone.utc) - datetime.fromisoformat(ts)).total_seconds())
    for n, unit in ((86400, "day"), (3600, "hour"), (60, "minute")):
        if secs >= n:
            k = secs // n
            return f"{k} {unit}{'s' if k != 1 else ''} ago"
    return "just now"


templates.env.filters["ago"] = _ago
BOT_USERNAME = lambda: os.getenv("TELEGRAM_BOT_USERNAME", "").lstrip("@")  # noqa: E731


@app.get("/records", response_class=HTMLResponse)
def records_page(request: Request, channel: str = "", verdict: str = ""):
    rows = history.list_checks(200, channel or None, verdict or None)
    return page(request, "records.html", rows=rows, stats=history.stats(), channel=channel, verdict=verdict, linked=links.chats_for(links.current_profile()),
                bot=BOT_USERNAME(), previews=history.preview_enabled())


@app.post("/api/telegram/code", dependencies=[Depends(limit_expensive)])
def telegram_code():
    code = links.new_code(links.current_profile())
    bot = BOT_USERNAME()
    return {"code": code, "expires_in": int(links.TTL), "bot": bot, "deep_link": f"https://t.me/{bot}?start={code}" if bot else ""}


@app.get("/api/telegram/status")
def telegram_status():
    return {"linked": links.chats_for(links.current_profile())}


@app.post("/api/telegram/unlink")
def telegram_unlink():
    return {"unlinked": links.unlink_profile(links.current_profile())}


class RecordIn(BaseModel):
    id: str


@app.post("/api/records/delete")
def records_delete(body: RecordIn):
    if not re.fullmatch(r"[0-9a-f]{12}", body.id):
        raise HTTPException(422, "invalid id")
    return {"deleted": history.delete(body.id)}


@app.post("/api/records/clear")
def records_clear():
    return {"deleted": history.delete_all()}


class PreviewIn(BaseModel):
    on: bool


@app.post("/api/settings/previews")
def settings_previews(body: PreviewIn):
    history.set_setting("store_preview", "1" if body.on else "0")
    if not body.on:  # turning previews off also removes the ones already kept
        from core.storage import db as _db

        with _db.connect() as c:
            c.execute("UPDATE check_log SET preview=''")
    return {"previews": history.preview_enabled()}


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
