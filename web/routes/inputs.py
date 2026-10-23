"""Other ways to add a message: read a screenshot, turn a voice note into text, and say which of those this server can do.
Both readers only return text for the person to look at, correct and then check. Nothing uploaded is stored, and nothing about it is logged."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from core import inputs, obs
from core.ai import llm
from core.inputs import audio, image
from core.inputs.errors import InputError
from web import ui
from web.deps import limit_expensive, request_lang
from web.uploads import UploadError, read_upload

router = APIRouter()

STATUS = {"too_big": 413, "bad_type": 415, "unreadable": 422, "no_text": 422, "unavailable": 503, "too_long": 413}
IMAGE_TOO_BIG = "That picture is too big. Please try a smaller screenshot."
AUDIO_TOO_BIG = "That voice note is too big. Please record a shorter one."
NO_FILE = "I couldn't open that file. Please try another one."
FAILED = "I couldn't read that. Please try again, or paste the text instead."
HINT = re.compile(r"[a-z]{2,3}(-[A-Za-z]{2,4})?")  # a language code such as en, ms, zh, zh-TW


def capabilities_now() -> dict:
    """What this server can do right now. Reading a screenshot needs the AI as well as the reader."""
    caps = inputs.capabilities()
    return {"image": bool(caps.get("image")) and llm.available(), "audio": bool(caps.get("audio"))}


@router.get("/api/capabilities")
def capabilities():
    return JSONResponse(capabilities_now(), headers={"Cache-Control": "no-store"})


def failure(err: InputError, lang: str) -> JSONResponse:
    return JSONResponse({"detail": ui.tr(err.message, lang), "code": err.code}, status_code=STATUS.get(err.code, 422), headers={"Cache-Control": "no-store"})


async def upload_of(request: Request, limit: int, too_big: str):
    try:
        return await read_upload(request, limit)
    except UploadError as e:
        raise InputError("too_big", too_big) if e.reason == "too_big" else InputError("unreadable", NO_FILE)


def unexpected(where: str, e: Exception, lang: str) -> JSONResponse:
    obs.emit({"kind": "error", "where": where, "type": type(e).__name__})  # the kind of failure only, never the file or the words in it
    return failure(InputError("unreadable", FAILED), lang)


@router.post("/api/read/image", dependencies=[Depends(limit_expensive)])
async def read_screenshot(request: Request):
    """multipart `file` (a PNG, JPEG, WebP or GIF) -> the message the picture shows, for the person to check before it is checked."""
    lang = request_lang(request)
    try:
        up = await upload_of(request, image.MAX_BYTES, IMAGE_TOO_BIG)
        r = await run_in_threadpool(image.read_image, up.data, lang=lang)
    except InputError as e:
        return failure(e, lang)
    except Exception as e:
        return unexpected("read_image", e, lang)
    return JSONResponse({"text": r.text, "sender": r.sender, "channel": r.channel, "app": r.app, "language": r.language, "links": list(r.links), "qr_urls": list(r.qr_urls), "legible": r.legible,
                         "note": ui.tr(r.note, lang) if r.note else ""}, headers={"Cache-Control": "no-store"})


@router.post("/api/read/audio", dependencies=[Depends(limit_expensive)])
async def read_voice(request: Request):
    """multipart `file` (a short recording) and an optional `lang` hint -> the words spoken. 503 when the server has no speech-to-text (the reader says so)."""
    lang = request_lang(request)
    try:
        up = await upload_of(request, audio.MAX_BYTES, AUDIO_TOO_BIG)
        hint = up.fields.get("lang", "").strip()
        r = await run_in_threadpool(audio.transcribe, up.data, mime=up.mime, lang_hint=hint if HINT.fullmatch(hint) else "")
    except InputError as e:
        return failure(e, lang)
    except Exception as e:
        return unexpected("transcribe", e, lang)
    return JSONResponse({"text": r.text, "language": r.language, "seconds": r.seconds}, headers={"Cache-Control": "no-store"})
