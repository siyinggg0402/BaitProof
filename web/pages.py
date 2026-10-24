"""Templates and page rendering shared by every route: the Jinja environment, what every page receives (language, translation helpers, the
language switcher, the strings its scripts need) and the `page()` helper."""
from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from core.ai import llm
from core.domain import characters, helplines, seasons
from core.lang import i18n
from core.storage import accounts, db, groups, links, model
from web import icons, ui
from web.deps import request_lang

BASE = Path(__file__).parent


def page_lang(request: Request) -> str:
    """The language of this page. The operator's pages stay in English."""
    return "en" if request.url.path.startswith("/admin") else request_lang(request)


def ui_context(request: Request) -> dict:
    """Added to every template: the language, the helpers that translate, the switcher and the strings the page's scripts need."""
    lang = page_lang(request)
    query = "&".join(p for p in request.url.query.split("&") if p and p.split("=")[0] not in ("share", "shared"))  # a one-time share token must not travel in the language links
    here = request.url.path + (f"?{query}" if query else "")
    return {
        "lang": lang, "html_lang": ui.HTML_LANG[lang], "list_sep": ui.LIST_SEP[lang], "labels": ui.labels(lang), "i18n_json": ui.i18n_json(lang),
        "STAGES": {k: ui.tr(v, lang) for k, v in ui.STAGES.items()}, "lang_next": "/" if request.url.path == "/check" else here,
        "langs": [(c, i18n.NAMES[c], ui.HTML_LANG[c]) for c in i18n.LANGS], "lang_short": ui.SHORT[lang],
        "account": None if request.url.path.startswith("/admin") else accounts.get(links.current_profile()), "multiuser": db.multiuser(),  # (the header shows who you are)
        "family_name": "" if request.url.path.startswith("/admin") else groups.name_of(links.current_profile()),
        "season": None if request.url.path.startswith("/admin") else seasons.current(lang),
    }


templates = Jinja2Templates(directory=BASE / "templates", context_processors=[ui_context])
templates.env.globals.update({"_": ui.translate, "_h": ui.translate_html, "tr_in": ui.translate_in, "STAGES": ui.STAGES, "help_lines": helplines.lines, "help_verified": helplines.VERIFIED})
templates.env.globals["zip_cells"] = zip
templates.env.globals.update({"icon": icons.icon, "avatar": icons.avatar, "sprite": icons.sprite})
templates.env.globals.update({"random_look": characters.random_look, "look_names": {"hair": characters.HAIR_NAMES, "outfit": characters.OUTFIT_NAMES, "accessory": characters.ACCESSORY_NAMES}})
templates.env.globals["look_tables"] = lambda: Markup(json.dumps(characters.tables()).replace("<", "\\u003c"))   # (the page reads the character tables from here)
templates.env.filters.update({
    "timestamp": lambda t: time.strftime("%H:%M:%S", time.localtime(t)),
    "ago": ui.ago_filter, "script": ui.script_filter, "trick_names": ui.trick_names, "plain": ui.plain,
})


def page(request: Request, name: str, **ctx):
    return templates.TemplateResponse(request, name, {"map": model.resilience_map(page_lang(request)), "ai": llm.available(), **ctx})
