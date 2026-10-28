"""The Baitproof website: app setup only. Pages and APIs live in web/routes/, templates and the translation helpers in web/pages.py and web/ui.py."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

import core  # noqa: F401  (loads .env)
from core.ai import llm
from core.inputs import audio
from core.pipelines.check import blocklist
from web import ui
from web.deps import add_security_headers, bind_profile, request_lang
from web.pages import BASE, page, templates
from web.routes import account, admin, check, duel, family, game, house, inputs, language, link, practice, push, pwa, records, road


@asynccontextmanager
async def lifespan(_app: FastAPI):
    llm.warmup()  # avoid the model's cold start landing on the first visitor
    audio.warmup()  # the same for the speech model, when server speech-to-text is installed (a no-op otherwise)
    blocklist.start_background()  # keeps the local copy of the public phishing list fresh (a no-op when the network tools are off)
    yield


app = FastAPI(title="Baitproof", dependencies=[Depends(bind_profile)], lifespan=lifespan)
add_security_headers(app)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


@app.exception_handler(StarletteHTTPException)
async def translated_errors(request: Request, exc: StarletteHTTPException):
    """The plain-language error messages ('That result has expired...') are shown to people, so they follow the visitor's language."""
    if isinstance(exc.detail, str) and request_lang(request) != "en":
        exc = StarletteHTTPException(exc.status_code, ui.tr(exc.detail, request_lang(request)), headers=exc.headers)
    return await http_exception_handler(request, exc)


async def healthz(_request: Request):
    """For an uptime monitor. Added at the Starlette level so it skips the per-visitor profile (a ping with no cookie would otherwise make a new database file each time)."""
    return JSONResponse({"ok": True}, headers={"Cache-Control": "no-store"})


app.add_route("/healthz", healthz, methods=["GET", "HEAD"])

for router in (language.router, check.router, inputs.router, records.router, practice.router, pwa.router, account.router, road.router, family.router, link.router, push.router, duel.router, house.router):
    app.include_router(router)
app.include_router(admin.mount(templates))
app.include_router(game.mount(page))
