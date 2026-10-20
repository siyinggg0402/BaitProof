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

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

import core  # noqa: F401  (loads .env)
from core.ai import llm
from core import obs
from core.domain import i18n
from core.domain.schemas import Drill
from core.pipelines import challenge, check, train
from core.storage import history, links, model
from web import cardimg, ui
from web import admin, game, results
from web.deps import LANG_CODES, LANG_COOKIE, add_security_headers, bind_profile, limit_expensive, request_lang, safe_next

BASE = Path(__file__).parent

@asynccontextmanager
async def lifespan(_app: FastAPI):
    llm.warmup()  # avoid the model's cold start landing on the first visitor
    yield


app = FastAPI(title="Baitproof", dependencies=[Depends(bind_profile)], lifespan=lifespan)
add_security_headers(app)

app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


def page_lang(request: Request) -> str:
    """The language of this page. The operator's pages stay in English."""
    return "en" if request.url.path.startswith("/admin") else request_lang(request)


def ui_context(request: Request) -> dict:
    """Added to every template: the language, the helpers that translate, the switcher and the strings the page's scripts need."""
    lang = page_lang(request)
    here = request.url.path + (f"?{request.url.query}" if request.url.query else "")
    return {
        "lang": lang, "html_lang": ui.HTML_LANG[lang], "list_sep": ui.LIST_SEP[lang], "labels": ui.labels(lang), "i18n_json": ui.i18n_json(lang),
        "STAGES": {k: ui.tr(v, lang) for k, v in ui.STAGES.items()}, "lang_next": "/" if request.url.path == "/check" else here,
        "langs": [(c, i18n.NAMES[c], ui.HTML_LANG[c]) for c in i18n.LANGS], "lang_short": ui.SHORT[lang],
    }


templates = Jinja2Templates(directory=BASE / "templates", context_processors=[ui_context])
templates.env.globals.update({"_": ui.translate, "_h": ui.translate_html, "tr_in": ui.translate_in, "STAGES": ui.STAGES})
templates.env.filters["timestamp"] = lambda t: __import__("time").strftime("%H:%M:%S", __import__("time").localtime(t))
app.include_router(admin.mount(templates))


@app.exception_handler(StarletteHTTPException)
async def translated_errors(request: Request, exc: StarletteHTTPException):
    """The plain-language error messages ('That result has expired...') are shown to people, so they follow the visitor's language."""
    if isinstance(exc.detail, str) and request_lang(request) != "en":
        exc = StarletteHTTPException(exc.status_code, ui.tr(exc.detail, request_lang(request)), headers=exc.headers)
    return await http_exception_handler(request, exc)

SESSIONS: "OrderedDict[str, dict[str, Drill]]" = OrderedDict()  # in-memory; answers never leave the server


def page(request: Request, name: str, **ctx):
    return templates.TemplateResponse(request, name, {"map": model.resilience_map(page_lang(request)), "ai": llm.available(), **ctx})


@app.get("/lang/{code}")
def set_language(request: Request, code: str, next: str = "/"):
    """Remember the visitor's language (a cookie, no account) and go back to where they were."""
    lang = LANG_CODES.get(code.lower())
    if lang is None:
        raise HTTPException(404, "Unknown language")
    resp = RedirectResponse(safe_next(next), status_code=303)
    resp.set_cookie(LANG_COOKIE, lang, max_age=31536000, path="/", samesite="lax", secure=request.url.scheme == "https")
    return resp


app.include_router(game.mount(page))


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return page(request, "index.html", result=None, text="")


@app.post("/check", response_class=HTMLResponse, dependencies=[Depends(limit_expensive)])
def do_check(request: Request, message: str = Form(...)):
    if not message.strip():
        raise HTTPException(400, "Paste a message to check.")
    result = check.check_message(message, lang=request_lang(request))
    history.add(result, "web", message)
    return page(request, "index.html", result=result, text=message[:4000])


class StreamIn(BaseModel):
    message: str


@app.post("/api/check/stream", dependencies=[Depends(limit_expensive)])
async def check_stream(request: Request, body: StreamIn):
    """Live view: Server-Sent Events, one per gate as it runs, then 'done' with the id of the finished check."""
    text = body.message.strip()
    if not text:
        raise HTTPException(400, "Paste a message to check.")
    q: "queue.Queue[tuple[str, object]]" = queue.Queue()
    lang = request_lang(request)
    ctx = contextvars.copy_context()  # carries the visitor's profile into the worker thread

    def work() -> None:
        try:
            r = ctx.run(check.check_message, text, True, lambda step: q.put(("step", step.model_dump())), True, lang)
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
    return templates.TemplateResponse(request, "_result.html", {"result": r})


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
templates.env.filters["ago"] = ui.ago_filter
templates.env.filters["script"] = ui.script_filter
templates.env.filters["trick_names"] = ui.trick_names
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
def train_start(request: Request):
    lang = request_lang(request)
    drills = train.build_session(lang=lang)
    sid = drills[0].id + "s" if drills else "empty"
    SESSIONS[sid] = {d.id: d for d in drills}
    while len(SESSIONS) > 200:
        SESSIONS.popitem(last=False)
    return {"session": sid, "items": [d.public() for d in drills], "map": model.resilience_map(lang)}


class AnswerIn(BaseModel):
    session: str
    item_id: str
    choice: int | None = None
    text: str = ""


@app.post("/api/train/answer")
def train_answer(request: Request, a: AnswerIn):
    drill = SESSIONS.get(a.session, {}).get(a.item_id)
    if not drill:
        raise HTTPException(404, "That practice session expired. Start a new one.")
    before = model.baitproof_score()
    lang = request_lang(request)
    g = train.grade(drill, a.choice, a.text, lang=lang)
    m = model.resilience_map(lang)
    return {"result": g.result, "note": g.note, "correct_index": drill.correct_index, "map": m, "delta": m["score"] - before}


@app.post("/challenge/new", dependencies=[Depends(limit_expensive)])
def challenge_new(request: Request):
    return RedirectResponse(f"/challenge/{challenge.create(lang=request_lang(request))}", status_code=303)


@app.get("/challenge/{cid}", response_class=HTMLResponse)
def challenge_page(request: Request, cid: str):
    items = challenge.get(cid)
    if items is None:
        raise HTTPException(404, "Challenge not found")
    return page(request, "challenge.html", cid=cid, items=[{"text": i["text"]} for i in items])


class SubmitIn(BaseModel):
    answers: list[bool | None]


@app.post("/api/challenge/{cid}/submit")
def challenge_submit(request: Request, cid: str, body: SubmitIn):
    items = challenge.get(cid)
    if items is None:
        raise HTTPException(404, "Challenge not found")
    res = challenge.score(items, body.answers)
    lang = request_lang(request)
    res["card_url"] = f"/card/{cid}?s={res['right']}" + ("" if lang == "en" else f"&lang={lang}")  # the link carries the language of its preview
    return res


@app.get("/card/{cid}", response_class=HTMLResponse)
def card(request: Request, cid: str, s: int = 0, lang: str | None = Query(None)):
    items = challenge.get(cid)
    if items is None:
        raise HTTPException(404, "Challenge not found")
    total = len(items)
    s = max(0, min(s, total))
    og_lang = LANG_CODES.get((lang or "").lower()) or request_lang(request)  # the preview follows the link's language, the page the visitor's
    return page(request, "card.html", cid=cid, pct=round(100 * s / total), right=s, total=total, og_lang=og_lang,
                url=str(request.url_for("challenge_page", cid=cid)),
                image=str(request.url_for("card_image", cid=cid)) + f"?s={s}" + ("" if og_lang == "en" else f"&lang={og_lang}"))


@app.get("/card-image/{cid}.png")
def card_image(cid: str, s: int = 0, lang: str = "en"):
    """Share-card image for link previews (Open Graph). Public: contains only the score, no message content."""
    items = challenge.get(cid)
    if items is None:
        raise HTTPException(404, "Challenge not found")
    s = max(0, min(s, len(items)))
    return Response(cardimg.render(round(100 * s / len(items)), s, len(items), LANG_CODES.get(lang.lower(), "en")), media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400"})


@app.get("/api/map")
def api_map(request: Request):
    return model.resilience_map(request_lang(request))
