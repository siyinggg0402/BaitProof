"""Where a message came from: cleaning what a screenshot reader or a Telegram forward reports, and saying it in the reader's language.

Everything here is UNVERIFIED context. It is shown back to the person (so they can see what we understood), given to the checker as a hint, and used to know which
company to look up. It never changes a verdict by itself."""
from __future__ import annotations

import re

from core.domain.schemas import CHANNELS, Origin
from core.lang.i18n import tr

_TEXT = re.compile(r"[^\w .,&()'/@+:#-]+", re.UNICODE)


def _clean(v: object, n: int) -> str:
    return " ".join(_TEXT.sub(" ", str(v or "")).split())[:n]


def make(channel: object = "", app: object = "", sender: object = "", forwarded_from: object = "") -> Origin | None:
    """An Origin from raw values (a model's words, a Telegram name): channel only from the fixed list, the rest reduced to plain name characters.
    None when nothing useful is left."""
    ch = str(channel or "").strip().lower()
    o = Origin(channel=ch if ch in CHANNELS else "", app=_clean(app, 60), sender=_clean(sender, 80), forwarded_from=_clean(forwarded_from, 80))
    return None if o.empty() else o


CHANNEL_PHRASE = {
    "sms": "an SMS", "whatsapp": "a WhatsApp message", "telegram": "a Telegram message", "wechat": "a WeChat message", "email": "an email",
    "social": "a social media post or message", "website": "a web page", "other": "",
}


def describe(o: Origin | None, lang: str) -> str:
    """One sentence for the person, e.g. 'A screen inside Tomoro Coffee' or 'An SMS from +65 9123 4567'. '' when we know nothing worth saying."""
    if o is None or o.empty():
        return ""
    T = lambda s, **kw: tr(s, lang, **kw)  # noqa: E731
    if o.forwarded_from:
        what = T("forwarded from {name}", name=o.forwarded_from)
        return T("Where it came from: {what}", what=what + (T(", it looks like {what}", what=_looks_like(o, T)) if _looks_like(o, T) else ""))
    what = _looks_like(o, T)
    return T("Where it came from: {what}", what=what) if what else ""


def _looks_like(o: Origin, T) -> str:
    if o.channel == "app" or (not o.channel and o.app):
        what = T("a screen inside {app}", app=o.app) if o.app else T("a screen inside an app or website")
        return T("{what}, from {sender}", what=what, sender=o.sender) if o.sender else what
    base = T(CHANNEL_PHRASE[o.channel]) if CHANNEL_PHRASE.get(o.channel) else ""
    if base and o.sender:
        return T("{what} from {sender}", what=base, sender=o.sender)
    if base:
        return base + (f" ({o.app})" if o.app else "")
    return T("a message from {sender}", sender=o.sender) if o.sender else (o.app or "")


def hint(o: Origin | None) -> str:
    """The line the checking model is shown (in English): context, flagged as unverified."""
    if o is None or o.empty():
        return ""
    parts = [f"channel: {o.channel}" if o.channel else "", f"app or brand shown: {o.app}" if o.app else "", f"sender shown: {o.sender}" if o.sender else "",
             f"forwarded from: {o.forwarded_from}" if o.forwarded_from else ""]
    return "WHERE IT CAME FROM (read from the screenshot or the forward; unverified, may be wrong; a hint about the kind of message, not evidence): " + "; ".join(p for p in parts if p)
