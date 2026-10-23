"""Checking a message: the home page, the form post, the live stream of gates, the result partial and the thumbs up/down."""
from __future__ import annotations

import asyncio
import contextvars
import inspect
import json
import queue
import re
import threading

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel

from core import obs
from core.inputs import image
from core.inputs.errors import InputError
from core.pipelines import check
from core.pipelines.check.origin import make as make_origin
from core.storage import history
from web import results
from web.deps import limit_expensive, request_lang
from web.pages import page, templates
from web.routes import pwa
from web.routes.inputs import capabilities_now

router = APIRouter()

SOURCES = ("text", "screenshot", "voice")  # how the message reached us


def clean_source(value: str | None) -> str:
    v = (value or "text").strip().lower()
    if v not in SOURCES:
        raise HTTPException(422, "That way of adding a message is not supported.")
    return v


def run_check(text: str, lang: str, source: str = "text", on_event=None, origin=None):
    """check_message, told where the message came from (the result then says so). Falls back to setting the fields itself on a core that does not take them yet."""
    params = inspect.signature(check.check_message).parameters
    extra = {k: v for k, v in (("source", source), ("read_text", text)) if source != "text" and k in params}
    if origin is not None:
        extra["origin"] = origin
    r = check.check_message(text, store=True, on_event=on_event, log=True, lang=lang, **extra)
    if source != "text":
        r.source, r.read_text = source, r.read_text or text
    return r


SHARE_NOTES = {
    "too_big": "That picture is too big. Please try a smaller screenshot.",
    "empty": "Nothing came through from the Share menu. Please paste the message instead.",
    "busy": "Baitproof is busy right now. Please try sharing again in a minute.",
}


async def shared_item(request: Request, item: dict) -> dict:
    """What the Share menu sent, turned into what the front page shows: the words (read from the picture, if there was one), where they came from, and
    whether to check them at once. A picture is read here, in the visitor's own request, because reading it costs a model call."""
    text = item["text"]
    if item["image"]:
        await limit_expensive(request)
        try:
            reading = await run_in_threadpool(image.read_image, item["image"], lang=request_lang(request))
            text = reading.text
            return {"text": text, "source": "screenshot", "origin": {"channel": reading.channel, "app": reading.app, "sender": reading.sender},
                    "autocheck": True, "notice": "Shared from another app. Checking it now…"}
        except InputError as e:
            if not text.strip():
                return {"notice": e.message}
        except Exception as e:  # noqa: BLE001 (a reader that is down: fall back to the words that came with it, or say so)
            obs.emit({"kind": "error", "where": "share_image", "type": type(e).__name__})
            if not text.strip():
                return {"notice": "I couldn't read that. Please try again, or paste the text instead."}
    return {"text": text, "autocheck": bool(text.strip()), "notice": "Shared from another app. Checking it now…" if text.strip() else SHARE_NOTES["empty"]}


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, share: str = "", shared: str = ""):
    ctx = {"result": None, "text": "", "source": "text", "caps": capabilities_now(), "notice": "", "autocheck": False, "origin": {}}
    if shared in SHARE_NOTES:
        ctx["notice"] = SHARE_NOTES[shared]
    elif share and (item := pwa.take(share)):
        ctx.update(await shared_item(request, item))
    return page(request, "index.html", **ctx)


@router.post("/check", response_class=HTMLResponse, dependencies=[Depends(limit_expensive)])
def do_check(request: Request, message: str = Form(...), source: str = Form("text"), origin_channel: str = Form(""), origin_app: str = Form(""), origin_sender: str = Form("")):
    source = clean_source(source)
    if not message.strip():
        raise HTTPException(400, "Paste a message to check.")
    result = run_check(message, request_lang(request), source, origin=make_origin(origin_channel, origin_app, origin_sender) if source == "screenshot" else None)
    history.add(result, "web", message)
    return page(request, "index.html", result=result, text=message[:4000], source=source, caps=capabilities_now())


class StreamIn(BaseModel):
    message: str
    source: str = "text"  # text | screenshot | voice
    origin_channel: str = ""  # what a screenshot showed about where the message came from (unverified; cleaned before use)
    origin_app: str = ""
    origin_sender: str = ""


@router.post("/api/check/stream", dependencies=[Depends(limit_expensive)])
async def check_stream(request: Request, body: StreamIn):
    """Live view: Server-Sent Events, one per gate as it runs, then 'done' with the id of the finished check."""
    source = clean_source(body.source)
    text = body.message.strip()
    if not text:
        raise HTTPException(400, "Paste a message to check.")
    q: "queue.Queue[tuple[str, object]]" = queue.Queue()
    lang = request_lang(request)
    ctx = contextvars.copy_context()  # carries the visitor's profile into the worker thread

    def work() -> None:
        try:
            r = ctx.run(run_check, text, lang, source, lambda step: q.put(("step", step.model_dump())),
                        make_origin(body.origin_channel, body.origin_app, body.origin_sender) if source == "screenshot" else None)
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


@router.get("/result/{check_id}", response_class=HTMLResponse)
def result_partial(request: Request, check_id: str):
    r = results.get(check_id)
    if r is None:
        raise HTTPException(404, "That result has expired. Please check the message again.")
    return templates.TemplateResponse(request, "_result.html", {"result": r})


class FeedbackIn(BaseModel):
    check_id: str
    rating: str


FEEDBACK_SEEN: set[tuple[str, str]] = set()


@router.post("/api/feedback")
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
