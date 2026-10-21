"""Telegram bot logic, kept free of any Telegram import so it is unit-testable offline.
One shared engine (core/) behind both channels (PLAN §5). Each chat gets its own anonymous profile.

Replies are plain data: a `Reply` is a message plus optional buttons, and tapping a button comes back to `on_callback` as a short string.
bot/telegram_bot.py only turns these into Telegram calls."""
from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field

from core.domain import privacy
from core.game import engine
from core.game import state as game_state
from core.lang import i18n
from core.lang.i18n import tactic_text, tr
from core.domain.schemas import CheckResult, Verdict
from core.domain.tactics import TACTICS
from core.pipelines import challenge
from core.pipelines.check import check_message
from core.storage import db, history, links, model

log = logging.getLogger(__name__)

WELCOME = ("Hi! I'm Baitproof 🛡️\n\nForward or paste any message you're unsure about and I'll tell you if it's a scam, "
           "show you the one giveaway, and add that trick to your practice.\n\n"
           "/quiz is a quick game: scam or not? (/quiz daily is today's Daily Challenge.)\n"
           "/challenge makes a link to send your family, to see if they can spot the scam too.\n\n"
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


@dataclass(frozen=True)
class Button:
    """An inline button. `data` comes back to on_callback when it is tapped; Telegram allows at most 64 bytes, and it never carries an answer."""
    label: str
    data: str

    def __post_init__(self) -> None:
        if len(self.data.encode()) > 64:
            raise ValueError("callback data is limited to 64 bytes")


@dataclass
class Reply:
    """One message to send. `buttons` is a list of rows. `edit` only matters for a button tap: rewrite the message that carried the button
    (which also drops its buttons) instead of sending a new one. `preview` lets Telegram unfurl a link in it (off unless asked for)."""
    text: str
    buttons: list[list[Button]] = field(default_factory=list)
    edit: bool = False
    preview: bool = False


@dataclass
class CallbackResult:
    """What a button tap leads to: a short pop-up for the person who tapped (may be empty) and the messages to show."""
    replies: list[Reply] = field(default_factory=list)
    toast: str = ""


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


def on_check(chat_id: int, text: str, lang_hint: str | None = None) -> list[Reply]:
    """A pasted or forwarded message: the verdict, and (when it taught a trick) buttons to practise it or to challenge the family."""
    linked = bind_chat(chat_id)
    L = chat_lang(lang_hint)
    if not text.strip():
        return [Reply(tr("Send me the message you want checked.", L or "en"))]
    result = check_message(text, lang=L)
    history.add(result, "telegram", text)  # the record: verdict, tricks, giveaway and a short redacted preview, never the raw message
    out = format_result(result)
    if linked and web_url():
        out += "\n\n" + tr("🗂 Saved to your records: {url}", result.lang, url=web_url("/records"))
    return [Reply(out[:4000], _practice_buttons(result.lang) if result.added_to_training else [])]


def on_text(chat_id: int, text: str, lang_hint: str | None = None) -> str:
    """on_check's message text alone (no buttons)."""
    return on_check(chat_id, text, lang_hint)[0].text


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


# ---------------------------------------------------------------- quiz and family challenge
# Callback data (Telegram: at most 64 bytes, and it only ever says WHICH button, never the answer):
#   q:<round id, 12 hex>:<question number>:<s|f|u>   an answer: scam, looks fine (safe), check first (unsure)
#   qn                                                start a new quick quiz (the Play again / Quick quiz buttons)
#   ch                                                make a family challenge (the Challenge my family buttons)
QUIZ_NEW, CHALLENGE = "qn", "ch"
CHOICES = {"s": "scam", "f": "safe", "u": "unsure"}
_ANSWER = re.compile(r"q:([0-9a-f]{12}):([0-9]{1,2}):([sfu])")
QUIZ_LEN = 5  # the engine's Rush round has 8 messages; a chat round is 5
QUIZ_LIMIT = (12, 600.0)  # round starts per chat: how many in how many seconds
CHALLENGE_LIMIT = (5, 3600.0)
ZWSP = chr(0x200B)  # a zero-width space


@dataclass
class _Quiz:
    round_id: str
    lang: str


_ACTIVE: "OrderedDict[int, _Quiz]" = OrderedDict()  # the one quiz each chat is playing; it lives in memory next to the engine's rounds
_ACTIVE_MAX = 5000
RATE: dict[str, list[float]] = {}
_LOCK = threading.RLock()  # the engine's rounds and the game state are read-modify-write, so one tap at a time


def _rate_limited(kind: str, chat_id: int, limit: tuple[int, float]) -> bool:
    """True if this chat has already started `limit[0]` of these within `limit[1]` seconds. Only allowed starts are counted."""
    now, (n, window) = time.time(), limit
    with _LOCK:
        recent = [t for t in RATE.get(f"{kind}:{chat_id}", []) if now - t < window]
        if len(recent) >= n:
            RATE[f"{kind}:{chat_id}"] = recent
            return True
        RATE[f"{kind}:{chat_id}"] = recent + [now]
        if len(RATE) > 5000:  # forget chats that have been quiet for longer than any window
            for k in [k for k, v in RATE.items() if not v or now - v[-1] > 3600]:
                RATE.pop(k, None)
        return False


def _inert(text: str) -> str:
    """The quiz quotes real-looking scams: break any link in them with invisible spaces so Telegram does not make it tappable."""
    return privacy.URL_RE.sub(lambda m: m.group(0).replace(".", "." + ZWSP).replace("://", ":" + ZWSP + "//"), text)


def _practice_buttons(lang: str) -> list[list[Button]]:
    return [[Button("🎮 " + tr("Quick quiz", lang), QUIZ_NEW)], [Button("👪 " + tr("Challenge my family", lang), CHALLENGE)]]


def _trim(r: engine.Round, n: int = QUIZ_LEN) -> None:
    """Cut a freshly started round down to `n` messages, keeping the scams from the person's own circle first and up to two that are not scams
    (so 'scam' is never always right). Done before any answer, so the engine then counts, scores and finishes a round of `n`."""
    if len(r.items) <= n:
        return
    others = [i for i in r.items if i.truth != "scam"][:2]
    scams = sorted((i for i in r.items if i.truth == "scam"), key=lambda i: i.source != "yours")  # stable: otherwise the engine's own order
    keep = [i.id for i in others + scams[: n - len(others)]]
    keep += [i.id for i in r.items if i.id not in keep][: n - len(keep)]
    r.items = [i for i in r.items if i.id in keep]


def _remember(chat_id: int, quiz: _Quiz) -> None:
    _ACTIVE.pop(chat_id, None)
    _ACTIVE[chat_id] = quiz
    while len(_ACTIVE) > _ACTIVE_MAX:
        _ACTIVE.popitem(last=False)


def _header(r: engine.Round, i: int, L: str, item: dict) -> str:
    line = ("📅 " + tr("Daily Challenge", L) if r.mode == "daily" else "🎮 " + tr("Quick quiz", L)) + " · " + tr("{i} of {n}", L, i=i + 1, n=len(r.items))
    return line + ("\n👪 " + tr("From your circle", L) if item["yours"] else "")


def _question(r: engine.Round, i: int, L: str) -> Reply:
    item = engine.public(r, L)["items"][i]  # the message only: the truth, the giveaway and the tricks stay on the server
    lines = [_header(r, i, L, item), "", f"“{item['text']}”", "", tr("What is this message?", L)]
    if i == 0:
        lines.append(tr("“Check first” means you'd phone the sender on a number you already trust.", L))
        if r.mode == "daily" and game_state.get()["daily_done"] == game_state.today():
            lines.insert(1, tr("Done today ✓. You can replay it for fun.", L))
    row = [Button(f"{icon} " + tr(label, L), f"q:{r.id}:{i}:{code}") for icon, label, code in (("🚨", "Scam", "s"), ("✅", "Looks fine", "f"), ("🤔", "Check first", "u"))]
    return Reply(_inert("\n".join(lines))[:4000], [row])


def _feedback(r: engine.Round, i: int, res: dict, L: str) -> Reply:
    """The question again with its answer revealed, in place of the buttons: the outcome, the giveaway and what to do."""
    item = engine.public(r, L)["items"][i]
    if res["outcome"] == "correct":
        title = tr("✅ Nice catch!", L)
    elif res["outcome"] == "partial":
        title = tr("🟡 Careful is good!", L)
    else:
        title = tr("💡 That one was genuine", L) if res["false_alarm"] else tr("💡 Here's the tell", L)
    truth = {"scam": tr("This one is a scam.", L), "safe": tr("This one is genuine.", L),
             "unsure": tr("This one is worth checking first: it could be real or fake.", L)}[res["truth"]]
    lines = [_header(r, i, L, item), "", f"“{item['text']}”", "", title + (" " + tr("+{n} XP", L, n=res["xp"]) if res["xp"] else ""), truth]
    if res["tell"]:
        lines += ["", tr("Why it's fine: {tell}" if res["truth"] == "safe" else "The giveaway: {tell}", L, tell=res["tell"])]
    action = res["action"]
    if res["truth"] == "scam" and not action and r.items[i].tactic:  # the authored English messages have no next step of their own: the trick's own one stands in
        action = tactic_text(r.items[i].tactic, "action", L, TACTICS)
    if action and res["truth"] != "safe":
        lines += ["", tr("What to do: {action}", L, action=action)]
    return Reply(_inert("\n".join(lines))[:4000], edit=True)


def _summary(s: dict, L: str) -> Reply:
    st = s["state"]
    lines = [tr("🌟 Flawless round!", L) if s["perfect"] else tr("🎉 Round complete!", L),
             tr("Not one slip. Your family is lucky to have you.", L) if s["perfect"] else tr("Nice work. Each round makes the next scam easier to spot.", L), "",
             f"✅ {s['correct']}/{s['total']} " + tr("right", L),
             "⭐ " + tr("+{n} XP", L, n=s["xp_gained"]),
             "🏆 " + tr("Level {n} · {title}", L, n=st["level"], title=st["title"]) + (" (" if i18n.norm(L) == "en" else "（") + tr("{a} / {b} XP", L, a=st["xp_into_level"], b=st["xp_for_level"]) + (")" if i18n.norm(L) == "en" else "）")]
    if s["level_up"]:
        lines.append("⬆️ " + tr("Level up! You're now level {n}: {title}", L, n=st["level"], title=st["title"]))
    if st["streak"]:
        lines.append("🔥 " + tr("{n}-day streak", L, n=st["streak"]))
    if s["daily_bonus"]:
        lines.append("📅 " + tr("Daily Challenge complete: +50 XP bonus!", L))
    lines += [f"🏅 {b['title']} — {b['desc']}" for b in s["badges_new"]]
    lines.append("🛡️ " + tr("Baitproof score {n}", L, n=s["resilience"]))
    return Reply("\n".join(lines)[:4000], [[Button("🎮 " + tr("Play again", L), QUIZ_NEW)], [Button("👪 " + tr("Challenge my family", L), CHALLENGE)]])


def on_quiz(chat_id: int, arg: str = "", lang_hint: str | None = None) -> list[Reply]:
    """/quiz (or /play): a quick round aimed at the tricks this person is weakest at. /quiz daily: today's Daily Challenge, the same 6 messages
    for everyone (in each language). Restarts any quiz the chat was playing. Progress goes to the chat's profile, the same one the website uses."""
    bind_chat(chat_id)
    L = chat_lang(lang_hint) or "en"
    mode = "daily" if arg.strip().lower() == "daily" else "rush"
    with _LOCK:
        if _rate_limited("quiz", chat_id, QUIZ_LIMIT):
            return [Reply(tr("You're playing fast! Please wait a few minutes before starting another quiz.", L))]
        try:
            r = engine.start(mode, owner=links.current_profile(), lang=L)
        except engine.GameError as e:
            return [Reply(tr(str(e), L))]
        if mode == "rush":
            _trim(r)
        _remember(chat_id, _Quiz(r.id, L))
        return [_question(r, 0, L)]


def _on_answer(chat_id: int, round_id: str, i: int, code: str, lang_hint: str | None) -> CallbackResult:
    with _LOCK:
        quiz = _ACTIVE.get(chat_id)
        expired = CallbackResult([Reply(tr("That quiz expired. Send /quiz to start a new one.", (quiz.lang if quiz else chat_lang(lang_hint)) or "en"))])
        if quiz is None or quiz.round_id != round_id:  # an old round, a restarted one, or another chat's: never graded
            return expired
        L = quiz.lang
        try:
            r = engine.get(round_id, links.current_profile())  # the engine also insists the round belongs to this chat's profile
        except engine.GameError:
            _ACTIVE.pop(chat_id, None)
            return expired
        if i >= len(r.items):
            return CallbackResult(toast=tr("Sorry, I didn't understand that button.", L))
        if r.items[i].id in r.answered:  # a double tap, or a button left over on an older question
            return CallbackResult(toast=tr("Already answered.", L))
        if i != len(r.answered):  # the questions come one at a time
            return CallbackResult(toast=tr("Sorry, I didn't understand that button.", L))
        try:
            res = engine.answer(r, r.items[i].id, CHOICES[code], lang=L)
        except engine.GameError as e:
            return CallbackResult(toast=tr(str(e), L))
        replies = [_feedback(r, i, res, L)]
        if res["over"]:
            _ACTIVE.pop(chat_id, None)
            replies.append(_summary(engine.finish(r, L), L))
        else:
            replies.append(_question(r, i + 1, L))
        return CallbackResult(replies)


def on_challenge(chat_id: int, lang_hint: str | None = None) -> list[Reply]:
    """/challenge: make a family challenge and give back a message to forward (with its web link). Needs BAITPROOF_URL, which says where the site lives."""
    bind_chat(chat_id)
    L = chat_lang(lang_hint) or "en"
    if not web_url():
        return [Reply(tr("The family challenge needs a web address, but BAITPROOF_URL isn't set on this bot yet. Please ask whoever runs it to set it.", L))]
    if _rate_limited("challenge", chat_id, CHALLENGE_LIMIT):  # each one is a row in the shared database
        return [Reply(tr("You've made a few challenges already. Please wait a bit before making another one.", L))]
    url = web_url(f"/challenge/{challenge.create(lang=L)}")
    return [Reply(tr("Here's your family challenge. Forward the next message to a parent, grandparent or friend 👇", L)),
            Reply(tr("Can you spot the scam? 🕵️ It takes 2 minutes and needs no account: {url}\nScammers go after families like ours, so I'd feel better if you tried it. 🛡️", L, url=url),
                  preview=True)]


def on_callback(chat_id: int, data: str | None, lang_hint: str | None = None) -> CallbackResult:
    """A button was tapped. `data` is untrusted: anything that is not exactly one of our formats, or that belongs to a round this chat is not
    playing any more, is refused politely and grades nothing."""
    try:
        bind_chat(chat_id)
        if data == QUIZ_NEW:
            return CallbackResult(on_quiz(chat_id, "", lang_hint))
        if data == CHALLENGE:
            return CallbackResult(on_challenge(chat_id, lang_hint))
        m = _ANSWER.fullmatch(data) if isinstance(data, str) else None
        if m:
            return _on_answer(chat_id, m.group(1), int(m.group(2)), m.group(3), lang_hint)
        return CallbackResult(toast=tr("Sorry, I didn't understand that button.", chat_lang(lang_hint) or "en"))
    except Exception:  # a tap must never crash the bot
        log.exception("button tap failed")
        return CallbackResult(toast=tr("Something went wrong. Please try again.", chat_lang(lang_hint) or "en"))
