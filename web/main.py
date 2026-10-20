"""The Baitproof website: app setup only. Pages and APIs live in web/routes/, templates and the translation helpers in web/pages.py and web/ui.py."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

import core  # noqa: F401  (loads .env)
from core.ai import llm
from web import ui
from web.deps import add_security_headers, bind_profile, request_lang
from web.pages import BASE, page, templates
from web.routes import admin, check, game, language, practice, records


@asynccontextmanager
async def lifespan(_app: FastAPI):
    llm.warmup()  # avoid the model's cold start landing on the first visitor
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


for router in (language.router, check.router, records.router, practice.router):
    app.include_router(router)
app.include_router(admin.mount(templates))
app.include_router(game.mount(page))
