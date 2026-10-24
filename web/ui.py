"""Language support for the pages: the helpers templates call (`_`, `_h`), the strings the browser's JavaScript needs, and the language switcher.

English text is the key (see core.lang.i18n). A page in English carries no dictionary at all; a Chinese page embeds only the strings its own
scripts ask for (`t("...")` in web/static/js), so it stays small."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from jinja2 import pass_context
from markupsafe import Markup

from core.lang import i18n
from core.lang.text import to_simplified
from core.domain.tactics import TACTICS

JS_DIR = Path(__file__).parent / "static" / "js"
HTML_LANG = {"en": "en", "zh": "zh-Hans", "zh-Hant": "zh-Hant", "ms": "ms", "ta": "ta"}  # the value of <html lang>
SPEECH_LANG = {"en": "en", "zh": "zh-CN", "zh-Hant": "zh-TW", "ms": "ms-MY", "ta": "ta-IN"}
SHORT = {"en": "EN", "zh": "简体", "zh-Hant": "繁體", "ms": "BM", "ta": "தமிழ்"}  # what the switcher shows for the current language
LIST_SEP = {"en": ", ", "zh": "、", "zh-Hant": "、", "ms": ", ", "ta": ", "}
STAGES = {  # plain-language names for the pipeline's stages (the "How I decided" list)
    "ingest": "Read the message", "triage": "Checked how you're doing", "intent": "Worked out what it asks of you", "tools": "Checked links and numbers",
    "analysis": "AI review", "grounding": "Verified claims against the message", "arbiter": "Weighed the evidence", "loop": "Investigated further",
    "second-look": "Took a second look", "sufficiency": "Confidence check", "critic": "Second reviewer", "output": "Final safety checks",
    "flywheel": "Added to your practice", "guard": "Safety net"}

# Where the shared Simplified-to-Traditional table picks the wrong character for a word we use ("分钟" is 分鐘, not 分鍾; "复制" is 複製, not 複制).
_HANT_FIXES = (("分鍾", "分鐘"), ("複制", "複製"))


def tr(text: str, lang: str = "en", **kw) -> str:
    """i18n.tr, plus the few Traditional spellings the shared table gets wrong."""
    out = i18n.tr(text, lang, **kw)
    if i18n.norm(lang) == "zh-Hant":
        for wrong, right in _HANT_FIXES:
            out = out.replace(wrong, right)
    return out


# t("..."), t(`...`): the English strings the scripts translate. Read from the files, so a new string never has to be registered twice.
_T_CALL = re.compile(r'(?<![\w.$])t\(\s*("(?:[^"\\\n]|\\.)*"|`[^`$\\]*`)')


@lru_cache(maxsize=1)
def js_keys() -> tuple[str, ...]:
    keys: dict[str, None] = {}
    for f in sorted(JS_DIR.glob("*.js")):
        for m in _T_CALL.finditer(f.read_text(encoding="utf-8")):
            lit = m.group(1)
            keys[json.loads(lit) if lit[0] == '"' else lit[1:-1]] = None
    return tuple(keys)


def _safe_json(obj) -> str:
    """JSON that is safe inside a <script> block: no '</script>', no HTML comment openers, no line separators."""
    return (json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


@lru_cache(maxsize=8)
def i18n_json(lang: str) -> str:
    """The `<script type="application/json" id="i18n">` payload for the scripts; empty for English (nothing to translate)."""
    lang = i18n.norm(lang)
    if lang == "en":
        return ""
    d = {k: tr(k, lang) for k in js_keys()}
    for tid, v in TACTICS.items():  # the trick names shown by scripts are the same ones the server shows
        d[v["label"]] = i18n.tactic_text(tid, "label", lang, TACTICS)
    return _safe_json({"lang": lang, "speech": SPEECH_LANG[lang], "dict": {k: v for k, v in d.items() if v != k}})


def labels(lang: str) -> dict[str, str]:
    return {tid: i18n.tactic_text(tid, "label", lang, TACTICS) for tid in TACTICS}


@pass_context
def translate(ctx, text: str, **kw) -> str:
    """{{ _("English text", name=value) }} in the page's language."""
    return tr(text, ctx.get("lang", "en"), **kw)


@pass_context
def translate_html(ctx, text: str, **kw) -> Markup:
    """Like `_`, for a string that carries trusted markup ('We keep the {tricks} ...'); the values in `kw` are escaped unless already Markup."""
    out = Markup(tr(text, ctx.get("lang", "en")))
    return out.format(**kw) if kw else out


# Emoji and pictograph symbols. The website draws icons instead (web/icons.py); text that is also written for chat apps (the Telegram bot, a family summary, the
# headline of a result) keeps its emoji there, and passes through `plain` on its way to a page.
_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\u2300-\u23FF\u25A0-\u25FF\uFE0F\u200D]")


def plain(text) -> str:
    return "\n".join(re.sub(r"[ \t]{2,}", " ", _EMOJI.sub("", line)).strip() for line in str(text or "").split("\n"))


def translate_in(lang: str, text: str, **kw) -> str:
    return tr(text, lang, **kw)


def ago(ts: str, lang: str = "en") -> str:
    from datetime import datetime, timezone

    secs = int((datetime.now(timezone.utc) - datetime.fromisoformat(ts)).total_seconds())
    for n, unit in ((86400, "day"), (3600, "hour"), (60, "minute")):
        if secs >= n:
            k = secs // n
            if lang == "en":
                return f"{k} {unit}{'s' if k != 1 else ''} ago"
            return tr(f"{{k}} {unit}s ago", lang, k=k)
    return tr("just now", lang)


@pass_context
def ago_filter(ctx, ts: str) -> str:
    return ago(ts, ctx.get("lang", "en"))


@pass_context
def script_filter(ctx, text: str) -> str:
    """Show Chinese text that was stored in the other script (a record kept while the page was Traditional, say) in the visitor's own."""
    lang = ctx.get("lang", "en")
    return i18n.to_traditional(text) if lang == "zh-Hant" else to_simplified(text) if lang == "zh" else text


@pass_context
def trick_names(ctx, ids) -> str:
    """'Rushing you, Fake website address' in the page's language, from a list of trick ids."""
    names = labels(ctx.get("lang", "en"))
    return LIST_SEP[ctx.get("lang", "en")].join(names.get(i, i) for i in ids)
