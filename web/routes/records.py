"""Records (everything checked on the website and in Telegram), the Telegram link, and the privacy settings."""
from __future__ import annotations

import os
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from core.storage import db, history, links
from web.deps import limit_expensive
from web.pages import page

router = APIRouter()


def bot_username() -> str:
    return os.getenv("TELEGRAM_BOT_USERNAME", "").lstrip("@")


@router.get("/records", response_class=HTMLResponse)
def records_page(request: Request, channel: str = "", verdict: str = ""):
    rows = history.list_checks(200, channel or None, verdict or None)
    return page(request, "records.html", rows=rows, stats=history.stats(), channel=channel, verdict=verdict, linked=links.chats_for(links.current_profile()),
                bot=bot_username(), previews=history.preview_enabled())


@router.post("/api/telegram/code", dependencies=[Depends(limit_expensive)])
def telegram_code():
    code = links.new_code(links.current_profile())
    bot = bot_username()
    return {"code": code, "expires_in": int(links.TTL), "bot": bot, "deep_link": f"https://t.me/{bot}?start={code}" if bot else ""}


@router.get("/api/telegram/status")
def telegram_status():
    return {"linked": links.chats_for(links.current_profile())}


@router.post("/api/telegram/unlink")
def telegram_unlink():
    return {"unlinked": links.unlink_profile(links.current_profile())}


class RecordIn(BaseModel):
    id: str


@router.post("/api/records/delete")
def records_delete(body: RecordIn):
    if not re.fullmatch(r"[0-9a-f]{12}", body.id):
        raise HTTPException(422, "invalid id")
    return {"deleted": history.delete(body.id)}


@router.post("/api/records/clear")
def records_clear():
    return {"deleted": history.delete_all()}


class PreviewIn(BaseModel):
    on: bool


@router.post("/api/settings/previews")
def settings_previews(body: PreviewIn):
    history.set_setting("store_preview", "1" if body.on else "0")
    if not body.on:  # turning previews off also removes the ones already kept
        with db.connect() as c:
            c.execute("UPDATE check_log SET preview=''")
    return {"previews": history.preview_enabled()}
