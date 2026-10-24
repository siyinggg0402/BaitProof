"""A glance at your own game, for the pages that show it (the home page and the Train page): your character, level, streak and the XP you can spend in the house."""
from __future__ import annotations

from fastapi import Request

from core.game import house, looks
from core.game import state as gs
from core.storage import links
from web.deps import request_lang


def glance(request: Request) -> dict:
    s = gs.summary(lang=request_lang(request))
    return {"level": s["level"], "title": s["title"], "into": s["xp_into_level"], "need": s["xp_for_level"], "streak": s["streak"], "rounds": s["rounds"],
            "daily_done": s["daily_done"], "balance": house.balance(), "look": looks.character(links.current_profile())}
