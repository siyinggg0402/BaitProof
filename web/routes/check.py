"""Checking a message: the home page, the form post, the live stream of gates, the result partial and the thumbs up/down."""
from __future__ import annotations

import asyncio
import contextvars
import json
import queue
import re
import threading

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from core import obs
from core.pipelines import check
from core.storage import history
from web import results
from web.deps import limit_expensive, request_lang
from web.pages import page, templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return page(request, "index.html", result=None, text="")


@router.post("/check", response_class=HTMLResponse, dependencies=[Depends(limit_expensive)])
def do_check(request: Request, message: str = Form(...)):
    if not message.strip():
        raise HTTPException(400, "Paste a message to check.")
    result = check.check_message(message, lang=request_lang(request))
    history.add(result, "web", message)
    return page(request, "index.html", result=result, text=message[:4000])


class StreamIn(BaseModel):
    message: str


@router.post("/api/check/stream", dependencies=[Depends(limit_expensive)])
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
