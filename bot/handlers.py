"""Telegram bot logic, kept free of any Telegram import so it is unit-testable offline.
One shared engine (core/) behind both channels (PLAN §5). Each chat gets its own anonymous profile."""
from __future__ import annotations

import hashlib
import os

from core.lang import i18n
from core.lang.i18n import tactic_text, tr
from core.domain.schemas import CheckResult, Verdict
from core.domain.tactics import TACTICS
from core.pipelines.check import check_message
from core.storage import db, history, links, model

WELCOME = ("Hi! I'm Baitproof 🛡️\n\nForward or paste any message you're unsure about and I'll tell you if it's a scam, "
           "show you the one giveaway, and add that trick to your practice.\n\n"
           "/link CODE connects this chat to your Baitproof web profile, so everything you check here shows up in your records.\n"
           "/history shows your latest checks, /score your Baitproof score, /unlink disconnects.\n"
           "/lang chooses the language: /lang en, /lang zh (简体中文) or /lang zh-Hant (繁體中文).\n"
           "I keep the tricks I see, not your messages.")
ICON = {Verdict.SCAM: "🚨", Verdict.LIKELY_SCAM: "⚠️", Verdict.SAFE: "✅", Verdict.UNSURE: "❓", Verdict.VICTIM: "💛"}


def bind_chat(chat_id: int) -> bool:
    """Point storage at this chat's profile. A LINKED chat uses the web profile it was linked to (same records, practice and score);
    an unlinked one gets its own anonymous profile. Returns True if linked. Isolation needs BAITPROOF_MULTIUSER=1 on a shared deploy."""
    linked = links.profile_for_chat(chat_id)
    db.set_profile(linked if linked else hashlib.sha256(f"tg:{chat_id}".encode()).hexdigest()[:32])  # 'local' is not a valid id: stays on the default DB
    return linked is not None


def chat_lang(hint: str | None = None) -> str | None:
    """The language to answer in, for the chat bound by bind_chat(): the chat's own /lang choice, else Telegram's language_code, else None
    (None means 'answer a message in its own language'). Needs bind_chat first: the choice lives in this chat's profile settings."""
    chosen = history.get_setting("tg_lang", "")
    if chosen:
        return i18n.norm(chosen)
    return i18n.norm(hint) if hint else None


def web_url(path: str = "") -> str:
    base = os.getenv("BAITPROOF_URL", "").rstrip("/")
    return f"{base}{path}" if base else ""


ATTEMPTS: dict[str, list[float]] = {}


def _too_many_attempts(chat_id: int) -> bool:
    """A guess limiter for link codes: 5 tries per chat per 10 minutes."""
    import time

    now = time.time()
    tries = [t for t in ATTEMPTS.get(str(chat_id), []) if now - t < 600]
    tries.append(now)
    ATTEMPTS[str(chat_id)] = tries
    return len(tries) > 5


def format_result(r: CheckResult) -> str:
    L = r.lang
    lines = [r.headline]
    if r.tell:
        lines += ["", tr("The giveaway: {tell}", L, tell=r.tell)]
    if r.action:
        lines += ["", tr("What to do: {action}", L, action=r.action)]
    if r.added_to_training:
        lines += ["", tr("📚 Added to your practice: {tricks}", L, tricks=_sep(L).join(tactic_text(t, "label", L, TACTICS) for t in r.added_to_training))]
    return "\n".join(lines)[:4000]


def _sep(lang: str) -> str:
    return ", " if i18n.norm(lang) == "en" else "、"


def on_text(chat_id: int, text: str, lang_hint: str | None = None) -> str:
    linked = bind_chat(chat_id)
    L = chat_lang(lang_hint)
    if not text.strip():
        return tr("Send me the message you want checked.", L or "en")
    result = check_message(text, lang=L)
    history.add(result, "telegram", text)  # the record: verdict, tricks, giveaway and a short redacted preview, never the raw message
    out = format_result(result)
    if linked and web_url():
        out += "\n\n" + tr("🗂 Saved to your records: {url}", result.lang, url=web_url("/records"))
    return out[:4000]


def on_start(chat_id: int, payload: str = "", lang_hint: str | None = None) -> str:
    """/start, optionally with a link code (the web page offers a one-tap t.me link that carries it)."""
    if payload.strip():
        return on_link(chat_id, payload, lang_hint)
    bind_chat(chat_id)
    return tr(WELCOME, chat_lang(lang_hint) or "en")


def on_link(chat_id: int, code: str, lang_hint: str | None = None) -> str:
    bind_chat(chat_id)
    L = chat_lang(lang_hint) or "en"
    if not code.strip():
        return tr("Send /link followed by the 6-character code from the Records page on Baitproof, for example /link K7M2QX.", L)
    if _too_many_attempts(chat_id):
        return tr("Too many tries. Please wait a few minutes and get a fresh code from the website.", L)
    profile = links.redeem(code, chat_id)
    if profile is None:
        return tr("That code didn't work. It may have expired (they last 10 minutes) or been used already. Get a fresh one from the Records page.", L)
    bind_chat(chat_id)
    L = chat_lang(lang_hint) or "en"  # a linked chat now uses the web profile, which may hold its own language choice
    return (tr("✅ Linked! Everything you check here now shows up in your Baitproof records, and the tricks you meet go into your practice.", L)
            + ("\n\n" + tr("See them: {url}", L, url=web_url("/records")) if web_url() else ""))


def on_unlink(chat_id: int, lang_hint: str | None = None) -> str:
    bind_chat(chat_id)
    L = chat_lang(lang_hint) or "en"
    return tr("Disconnected. Your records stay in your Baitproof profile.", L) if links.unlink_chat(chat_id) else tr("This chat wasn't linked.", L)


def on_lang(chat_id: int, arg: str, lang_hint: str | None = None) -> str:
    """/lang en | zh | zh-Hant: remembered for this chat (in its profile settings)."""
    bind_chat(chat_id)
    a = arg.strip()
    if a.lower() not in ("en", "zh", "zh-hans", "zh-cn", "zh-hant", "zh-tw", "zh-hk", "cn", "tw"):
        return tr("Send /lang en, /lang zh or /lang zh-Hant.", chat_lang(lang_hint) or "en")
    chosen = i18n.norm("zh-Hant" if a.lower() in ("tw", "zh-tw", "zh-hk", "zh-hant") else a)
    history.set_setting("tg_lang", chosen)
    return {"en": "Language set to English.", "zh": "已切换为简体中文。", "zh-Hant": "已切換為繁體中文。"}[chosen]


def on_history(chat_id: int, n: int = 5, lang_hint: str | None = None) -> str:
    bind_chat(chat_id)
    L = chat_lang(lang_hint) or "en"
    rows = history.list_checks(n)
    if not rows:
        return tr("No checks yet. Paste or forward a message and I'll check it.", L)
    lines = [tr("Your latest checks:", L)]
    for r in rows:
        tricks = _sep(L).join(tactic_text(t, "label", L, TACTICS) for t in r["tactics"] if t in TACTICS)
        what = (r["preview"] or r["headline"])[:70] + (f" ({tricks})" if tricks else "")
        lines.append(tr("{icon} {date} via {channel}: {what}", L, icon=ICON.get(Verdict(r["verdict"]), "•"), date=r["ts"][:10], channel=tr(r["channel"], L), what=what))
    return "\n".join(lines) + ("\n\n" + tr("All of them: {url}", L, url=web_url("/records")) if web_url() else "")


def on_score(chat_id: int, lang_hint: str | None = None) -> str:
    bind_chat(chat_id)
    L = chat_lang(lang_hint) or "en"
    m = model.resilience_map()
    weak = [tactic_text(t["id"], "label", L, TACTICS) for t in m["tactics"] if t["level"] == "weak"]
    out = tr("Your Baitproof score: {score}/100", L, score=m["score"])
    if weak:
        out += "\n" + tr("Weakest tricks: {tricks}", L, tricks=_sep(L).join(weak))
    if m["due"]:
        out += "\n" + tr("{n} trick(s) due for a refresher.", L, n=m["due"])
    url = os.getenv("BAITPROOF_URL")
    return out + ("\n\n" + tr("Practise here: {url}", L, url=f"{url}/train") if url else "")


def nudge_text(chat_id: int) -> str | None:
    """Daily nudge: only when something is actually due, so it never becomes noise."""
    bind_chat(chat_id)
    m = model.resilience_map()
    if not m["due"]:
        return None
    url = os.getenv("BAITPROOF_URL", "")
    return tr("🛡️ {n} scam trick(s) are due for a one-minute refresher.", chat_lang() or "en", n=m["due"]) + (f" {url}/train" if url else "")
