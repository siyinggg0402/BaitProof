"""Telegram bot logic, kept free of any Telegram import so it is unit-testable offline.
One shared engine (core/) behind both channels (PLAN §5). Each chat gets its own anonymous profile.

Replies are plain data: a `Reply` is a message plus optional buttons, and tapping a button comes back to `on_callback` as a short string.
bot/telegram_bot.py only turns these into Telegram calls."""
from __future__ import annotations

import hashlib
import inspect
import logging
import os
import queue
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field

from core import obs
from core.domain import helplines, privacy
from core.game import engine
from core.game import state as game_state
from core.inputs import audio, image
from core.inputs.errors import InputError
from core.lang import i18n
from core.lang.i18n import tactic_text, tr
from core.domain.schemas import CheckResult, LinkInfo, Origin, Verdict
from core.domain.tactics import TACTICS
from core.pipelines import challenge
from core.pipelines.check import check_message
from core.pipelines.check.origin import make as make_origin
from core.storage import accounts, db, family, history, links, model

log = logging.getLogger(__name__)

WELCOME = ("Hi! I'm Finn 🐟, Baitproof's scam-spotting fish. I never take the bait!\n\nForward or paste any message you're unsure about and I'll tell you if it's a scam, "
           "show you the one giveaway, and add that trick to your practice.\n"
           "You can also send a screenshot or a voice note.\n\n"
           "/quiz is a quick game: scam or not? (/quiz daily is today's Daily Challenge.)\n"
           "/challenge makes a link to send your family, to see if they can spot the scam too.\n\n"
           "/link CODE connects this chat to your Baitproof web profile, so everything you check here shows up in your records.\n"
           "/history shows your latest checks, /score your Baitproof score, /unlink disconnects.\n"
           "/report shows who to call, and where to report a scam, if you have already paid or shared something.\n"
           "/family lets someone you trust get a short note when you meet a scam (they never see your messages). /safeword explains a simple trick against fake \"it's me\" messages.\n"
           "/lang chooses the language: /lang en, /lang ms (Bahasa Melayu), /lang ta (தமிழ்), /lang zh (简体中文) or /lang zh-Hant (繁體中文).\n"
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
    """The verdict, the giveaway and what to do; then (when the message had links) the link report, and the tricks added to practice.
    If it ever has to be cut to fit Telegram's limit, the end of the giveaway goes first: the link report and the practice line stay."""
    L = r.lang
    sections = [r.headline]
    if r.tell:  # the giveaway often quotes the scam's link: keep it readable but not tappable
        sections.append(tr("The giveaway: {tell}", L, tell=_defang(r.tell)))
    if r.action:
        sections.append(tr("What to do: {action}", L, action=_defang(r.action)))
    tail = []
    if r.origin_note:  # where it seems to have come from: said back, so the person can see what was understood
        tail.append("📍 " + _defang(r.origin_note))
    if r.verdict == Verdict.SAFE:  # a "safe" is only worth something if it says what it rests on
        proofs = [e.claim for e in r.evidence if e.kind == "tool" and e.supports == "safe" and e.source in ("org-verified", "domain_owner", "brand_lookup", "established-links")][:2]
        if proofs:
            tail.append("🔎 " + tr("What I checked:", L) + " " + "; ".join(_defang(c) for c in proofs))
    if r.links:
        tail.append(format_links(r.links, L))
    if r.verdict in (Verdict.SCAM, Verdict.LIKELY_SCAM):
        tail.append(helplines.short(L))
    elif r.verdict == Verdict.VICTIM:  # someone who says they were fooled: the whole list, not a hint
        tail.append(helplines.text(L))
    if r.added_to_training:
        tail.append(tr("📚 Added to your practice: {tricks}", L, tricks=_sep(L).join(tactic_text(t, "label", L, TACTICS) for t in r.added_to_training)))
    end = "".join("\n\n" + s for s in tail)
    return "\n\n".join(sections)[: 4000 - len(end)] + end


def _sep(lang: str) -> str:
    return "、" if i18n.norm(lang) in ("zh", "zh-Hant") else ", "


def _checked(linked: bool, text: str, L: str | None, source: str = "text", origin: Origin | None = None, chat_id: int | None = None) -> tuple[CheckResult, Reply]:
    """Check `text` and record it. `source` says how the message reached us (text | screenshot | voice); for the last two `text` is what was READ or
    HEARD, and that is what the record's (redacted) preview comes from. Returns the result and the reply that shows it."""
    extra = {}
    accepted = inspect.signature(check_message).parameters
    if source != "text":  # tell the pipeline where the text came from, if this version of it knows how to take that
        extra = {k: v for k, v in (("source", source), ("read_text", text)) if k in accepted}
    if origin is not None:
        extra["origin"] = origin
    result = check_message(text, lang=L, **extra)
    if source != "text":  # and if it does not, say it here
        if result.source == "text":
            result.source = source
        result.read_text = result.read_text or text
    history.add(result, "telegram", text)  # the record: verdict, tricks, giveaway and a short redacted preview, never the raw message
    if chat_id is not None:
        _family_notify(result, chat_id)
    out = format_result(result)
    if linked and web_url():
        out += "\n\n" + tr("🗂 Saved to your records: {url}", result.lang, url=web_url("/records"))
    return result, Reply(out[:4000], _practice_buttons(result.lang) if result.added_to_training else [])


def on_check(chat_id: int, text: str, lang_hint: str | None = None, forwarded_from: str = "") -> list[Reply]:
    """A pasted or forwarded message: the verdict, and (when it taught a trick) buttons to practise it or to challenge the family.
    `forwarded_from` is who or what Telegram says a forwarded message came from (empty for a message typed or pasted in)."""
    linked = bind_chat(chat_id)
    L = chat_lang(lang_hint)
    if not text.strip():
        return [Reply(tr("Send me the message you want checked. 🐟", L or "en"))]
    return [_checked(linked, text, L, origin=make_origin(forwarded_from=forwarded_from), chat_id=chat_id)[1]]


def on_text(chat_id: int, text: str, lang_hint: str | None = None) -> str:
    """on_check's message text alone (no buttons)."""
    return on_check(chat_id, text, lang_hint)[0].text


def on_start(chat_id: int, payload: str = "", lang_hint: str | None = None) -> str:
    """/start, optionally with a link code (the web page offers a one-tap t.me link that carries it)."""
    if payload.strip():
        return on_link(chat_id, payload, lang_hint, tapped=True)
    bind_chat(chat_id)
    return tr(WELCOME, chat_lang(lang_hint) or "en")


def on_link(chat_id: int, code: str, lang_hint: str | None = None, tapped: bool = False) -> str:
    """/link CODE, or /start CODE from a tapped link. A tapped link never moves a chat that already belongs to another profile (someone could send you
    their link): you have to /unlink first, which is a choice you make yourself."""
    bind_chat(chat_id)
    L = chat_lang(lang_hint) or "en"
    if not code.strip():
        return tr("Send /link followed by the 6-character code from the Records page on Baitproof, for example /link K7M2QX.", L)
    if _too_many_attempts(chat_id):
        return tr("Too many tries. Please wait a few minutes and get a fresh code from the website.", L)
    if tapped:
        target, current = links.peek(code), links.profile_for_chat(chat_id)
        if target and current and current != target:
            return tr("This chat is already connected to a different Baitproof profile. Send /unlink first, then tap the link again.", L)
    profile = links.redeem(code, chat_id)
    if profile is None:
        return tr("That code didn't work. It may have expired (they last 10 minutes) or been used already. Get a fresh one from the Records page.", L)
    bind_chat(chat_id)
    L = chat_lang(lang_hint) or "en"  # a linked chat now uses the web profile, which may hold its own language choice
    who = accounts.get(profile)
    return (tr("✅ Linked! Everything you check here now shows up in your Baitproof records, and the tricks you meet go into your practice.", L)
            + ("\n\n" + tr("Connected to {name}. Not you? Send /unlink.", L, name=who["nickname"]) if who else "")
            + ("\n\n" + tr("See them: {url}", L, url=web_url("/records")) if web_url() else ""))


def on_unlink(chat_id: int, lang_hint: str | None = None) -> str:
    bind_chat(chat_id)
    L = chat_lang(lang_hint) or "en"
    return tr("Disconnected. Your records stay in your Baitproof profile.", L) if links.unlink_chat(chat_id) else tr("This chat wasn't linked.", L)


def on_lang(chat_id: int, arg: str, lang_hint: str | None = None) -> str:
    """/lang en | ms | ta | zh | zh-Hant: remembered for this chat (in its profile settings)."""
    bind_chat(chat_id)
    a = arg.strip()
    if a.lower() not in ("en", "ms", "bm", "malay", "ta", "tamil", "zh", "zh-hans", "zh-cn", "zh-hant", "zh-tw", "zh-hk", "cn", "tw"):
        return tr("Send /lang en, /lang ms, /lang ta, /lang zh or /lang zh-Hant.", chat_lang(lang_hint) or "en")
    chosen = i18n.norm("zh-Hant" if a.lower() in ("tw", "zh-tw", "zh-hk", "zh-hant") else a)
    history.set_setting("tg_lang", chosen)
    return {"en": "Language set to English.", "zh": "已切换为简体中文。", "zh-Hant": "已切換為繁體中文。", "ms": "Bahasa ditetapkan kepada Bahasa Melayu.", "ta": "மொழி தமிழாக மாற்றப்பட்டது."}[chosen]


def on_report(chat_id: int, lang_hint: str | None = None) -> str:
    """/report: who to call and where to report a scam (Singapore and Malaysia), in the chat's language."""
    bind_chat(chat_id)
    return helplines.text(chat_lang(lang_hint) or "en")


# ---------------------------------------------------------------- family alerts and the safe word
ALERTS: "queue.SimpleQueue[tuple[int, str]]" = queue.SimpleQueue()  # (chat id, text) to send to someone ELSE; the connector drains it after it has answered


def take_alerts() -> list[tuple[int, str]]:
    """Messages for other chats that the last checks produced (a family helper's note). The connector sends them."""
    out = []
    while True:
        try:
            out.append(ALERTS.get_nowait())
        except queue.Empty:
            return out


def _family_notify(r: CheckResult, chat_id: int) -> None:
    """Tell this person's family helpers (if they chose any) that they just met a scam, or may have been fooled. Only the verdict and the NAMES of the tricks
    go out: never the message, its words, its links or its numbers."""
    if r.verdict not in (Verdict.SCAM, Verdict.LIKELY_SCAM, Verdict.VICTIM):
        return
    profile = db._profile.get() or links.LOCAL
    helpers = [h for h in family.helpers_of(profile) if h["chat_id"] != str(chat_id)]
    if not helpers or not family.may_alert(profile):
        return
    for h in helpers:
        L = h["lang"] or "en"
        who = h["name"] or tr("A family member", L)
        if r.verdict == Verdict.VICTIM:
            text = tr("🚨 {who} may have already paid or shared something with a scammer. Please call them now. If money was sent, they should call their bank straight away. More: /report", L, who=who)
        else:
            tricks = _sep(L).join(tactic_text(t.id, "label", L, TACTICS) for t in r.tactics[:3])
            text = tr("👪 {who} just checked a message that looks like a scam.", L, who=who) + (" " + tr("Tricks: {tricks}.", L, tricks=tricks) if tricks else "")
            text += "\n" + tr("Why not give them a call, to check they're okay and haven't paid or shared anything? Tip: agree a family safe word (/safeword).", L)
        ALERTS.put((int(h["chat_id"]), text))


def on_family(chat_id: int, arg: str = "", lang_hint: str | None = None) -> str:
    """/family [name] makes a code for a family helper; /family off stops all alerts about you."""
    bind_chat(chat_id)
    L = chat_lang(lang_hint) or "en"
    profile = db._profile.get() or links.LOCAL
    if arg.strip().lower() == "off":
        gone = family.stop_for_owner(profile)
        for h in gone:
            ALERTS.put((int(h["chat_id"]), tr("You will no longer get family alerts about {who}.", h["lang"] or "en", who=h["name"] or tr("a family member", h["lang"] or "en"))))
        return tr("Done. Nobody gets alerts about your checks any more.", L) if gone else tr("Nobody was getting alerts about your checks.", L)
    if _too_many_attempts(chat_id):
        return tr("Too many tries. Please wait a few minutes and get a fresh code from the website.", L)
    code = family.new_code(profile, chat_id, arg)
    n = family.count(profile)
    out = tr("👪 Family alerts\n\nAsk someone you trust to send me this in their own chat (it works for 10 minutes):\n\n/guard {code}\n\nThen, when you check a message that looks like a scam, they get a short note that you checked one and which tricks it uses. They never see your messages. Stop it any time with /family off.", L, code=code)
    if n:
        out += "\n\n" + tr("Right now {n} family helper(s) get these alerts.", L, n=n)
    return out


def on_guard(chat_id: int, arg: str = "", lang_hint: str | None = None, who: str = "") -> str:
    """/guard CODE: become a family helper for someone; /guard off: stop being one."""
    bind_chat(chat_id)
    L = chat_lang(lang_hint) or "en"
    a = arg.strip()
    if a.lower() == "off":
        left = family.stop_for_helper(chat_id)
        return tr("Done. You won't get family alerts any more.", L) if left else tr("You weren't getting any family alerts.", L)
    if not a:
        return tr("Send /guard followed by the 6-character code your family member got from /family, for example /guard K7M2QX. To stop getting alerts: /guard off.", L)
    if _too_many_attempts(chat_id):
        return tr("Too many tries. Please wait a few minutes and get a fresh code from the website.", L)
    got = family.redeem(a, chat_id, L)
    if got is None:
        return tr("That code didn't work. It may have expired (they last 10 minutes), been used already, or this person already has the most helpers. Ask them for a fresh one with /family.", L)
    ALERTS.put((int(got["owner_chat"]), tr("👪 {who} is now a family helper: they get a short note when you check something that looks like a scam, never your messages. Stop it any time with /family off.", chat_lang() or "en", who=(who or tr("Someone you invited", chat_lang() or "en")))))
    name = got["name"] or tr("them", L)
    return tr("👪 You're now a family helper for {name}. When they check a message that looks like a scam, I'll tell you, so you can give them a call. I never pass on what their messages say. To stop: /guard off.", L, name=name)


def on_safeword(chat_id: int, lang_hint: str | None = None) -> str:
    bind_chat(chat_id)
    return tr("🔑 A family safe word\n\nScammers copy voices and hijack chat accounts, so \"Hi Mum, it's me, I need money now\" can look and sound real. Agree ONE secret word with your family, in person. If anyone asks for money or codes in a hurry, even if it sounds just like them, ask for the safe word. No word, no money.\n\nNever type your safe word here, or in any chat.", chat_lang(lang_hint) or "en")


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
    return tr("🐟 Psst! {n} scam trick(s) are due for a one-minute refresher.", chat_lang() or "en", n=m["due"]) + (f" {url}/train" if url else "")


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


def _rate_limited(kind: str, chat_id: int, limit: tuple[int, float], count: bool = True) -> bool:
    """True if this chat has already started `limit[0]` of these within `limit[1]` seconds. Only allowed starts are counted
    (`count=False` just looks, for a check made before the work starts)."""
    now, (n, window) = time.time(), limit
    with _LOCK:
        recent = [t for t in RATE.get(f"{kind}:{chat_id}", []) if now - t < window]
        if len(recent) >= n:
            RATE[f"{kind}:{chat_id}"] = recent
            return True
        if count:
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
             "🏆 " + tr("Level {n} · {title}", L, n=st["level"], title=st["title"]) + (" (" if i18n.norm(L) in ("en", "ms", "ta") else "（") + tr("{a} / {b} XP", L, a=st["xp_into_level"], b=st["xp_for_level"]) + (")" if i18n.norm(L) == "en" else "）")]
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


# ---------------------------------------------------------------- screenshots, voice notes and the link report
# A picture or a voice note is turned into text by core.inputs and then checked like any pasted message. Neither the picture nor the audio is
# ever stored: they live in memory for the length of one call. Reading costs money (a vision model, a speech model), so each chat gets a modest
# hourly allowance of each. The words that were read are shown back (with every link made untappable) so the person can see what was understood.
IMAGE_LIMIT = (20, 3600.0)  # picture reads per chat per hour
VOICE_LIMIT = (20, 3600.0)  # voice notes per chat per hour
QUOTE_MAX = 700  # characters of the read text shown back
LINKS_SHOWN = 5  # links listed in a reply; the rest are counted
LINK_ICON = {"official": "✅", "known_phishing": "🚫", "lookalike": "⚠️", "shortener": "🔗", "suspicious": "🚫", "unverified": "❓", "established": "🏛️"}
_DOMAIN_DOT = re.compile(r"(?<=\w)\.(?=[^\W\d_]{2,}(?![^\W\d_]))")  # a dot before an ending of 2+ letters: how a bare domain such as dhl-parcel.ru looks (not 'e.g.' or '2.99')


def _defang(text: str) -> str:
    """Words from a scam (read from a screenshot, or heard) may hold links. Break each one, and each bare domain that Telegram would also make
    tappable, with invisible spaces. The text still reads the same."""
    return _DOMAIN_DOT.sub("." + ZWSP, _inert(text))


def _defang_all(text: str) -> str:
    """For a host or a URL on its own: every dot and the '//' are broken (this also covers an address made of numbers)."""
    return text.replace("://", ":" + ZWSP + "//").replace(".", "." + ZWSP)


def _short(text: str, n: int = QUOTE_MAX) -> str:
    t = text.strip()
    return t if len(t) <= n else t[:n].rstrip() + "…"


def _mb(n: int) -> str:
    return f"{n / 1_000_000:g}"


def format_links(found: list[LinkInfo], L: str) -> str:
    """The 'Links' part of a reply: one short line per link, an emoji for what we found, the address (never tappable) and a few words on it."""
    lines = [tr("🔗 Links", L)]
    for k in found[:LINKS_SHOWN]:
        line = f"{LINK_ICON.get(k.status, '❓')} {_defang_all(k.host)}"
        if k.label:
            line += " — " + _defang(k.label[:90])
        if k.expanded_to:
            line += " " + tr("→ really goes to {host}", L, host=_defang_all(k.expanded_to[:120]))
        lines.append(line)
    if len(found) > LINKS_SHOWN:
        lines.append(tr("…and {n} more link(s)", L, n=len(found) - LINKS_SHOWN))
    return "\n".join(lines)


def note_failure(where: str, e: BaseException) -> None:
    """Something unexpected went wrong while reading a picture or a voice note: say so in the logs (the kind of error only, never the content)."""
    log.error("could not handle %s", where, exc_info=e)
    obs.emit({"kind": "error", "where": f"bot.{where}", "type": type(e).__name__})


def sorry(chat_id: int, lang_hint: str | None = None) -> Reply:
    """The polite reply when something unexpected breaks. It must work even if the database is the thing that broke."""
    try:
        bind_chat(chat_id)
        L = chat_lang(lang_hint)
    except Exception:
        L = i18n.norm(lang_hint) if lang_hint else None
    return Reply(tr("Sorry, I couldn't read that. Please send the text.", L or "en"))


def _read_reply(head: str, text: str, L: str, sender: str = "", qr: list[str] | None = None, note: str = "") -> str:
    """'I read this:' and the words, then any caution from the reader."""
    lines = [head]
    if sender.strip():
        lines.append(tr("From: {sender}", L, sender=_defang(sender.strip()[:80])))
    if text:
        lines += ["", "“" + _defang(_short(text)) + "”"]
    lines += [tr("QR code in the picture: {url}", L, url=_defang_all(u[:200])) for u in (qr or [])[:3]]
    if note:
        lines += ["", tr(note, L)]
    return "\n".join(lines)[:4000]


def _image_blocked(chat_id: int, size: int | None, L: str, count: bool) -> Reply | None:
    """The reply that explains why a picture cannot be read right now, or None if it can. `size` may be None (Telegram did not say)."""
    if not image.available():
        return Reply(tr("Reading screenshots needs the AI, which is not switched on here. Paste the text instead.", L))
    if size is not None and size > image.MAX_BYTES:
        return Reply(tr("That picture is too big (the limit is {mb} MB). Please send a smaller one, or paste the text.", L, mb=_mb(image.MAX_BYTES)))
    if _rate_limited("image", chat_id, IMAGE_LIMIT, count):
        return Reply(tr("You've sent a lot of pictures. Please wait a while, or paste the text instead.", L))
    return None


def _voice_blocked(chat_id: int, size: int | None, seconds: float | None, L: str, count: bool) -> Reply | None:
    if not audio.available():
        return Reply(tr("Voice notes are not switched on here. Send the text or a screenshot instead.", L))
    if size is not None and size > audio.MAX_BYTES:
        return Reply(tr("That voice note is too big (the limit is {mb} MB). Please send a shorter one, or the text.", L, mb=_mb(audio.MAX_BYTES)))
    if seconds is not None and seconds > audio.MAX_SECONDS:
        return Reply(tr("That voice note is too long (the limit is {n} seconds). Please send a shorter one, or the text.", L, n=audio.MAX_SECONDS))
    if _rate_limited("voice", chat_id, VOICE_LIMIT, count):
        return Reply(tr("You've sent a lot of voice notes. Please wait a while, or send the text instead.", L))
    return None


def image_precheck(chat_id: int, file_size: int | None, lang_hint: str | None = None) -> list[Reply]:
    """Before downloading a picture from Telegram: [] to go ahead, or the reply that says why not (not switched on, too big, too many)."""
    bind_chat(chat_id)
    stop = _image_blocked(chat_id, file_size, chat_lang(lang_hint) or "en", count=False)
    return [stop] if stop else []


def voice_precheck(chat_id: int, file_size: int | None, seconds: float | None, lang_hint: str | None = None) -> list[Reply]:
    """The same for a voice note, which also has a length limit."""
    bind_chat(chat_id)
    stop = _voice_blocked(chat_id, file_size, seconds, chat_lang(lang_hint) or "en", count=False)
    return [stop] if stop else []


def on_image(chat_id: int, data: bytes, lang_hint: str | None = None, forwarded_from: str = "") -> list[Reply]:
    """A screenshot (the bytes of the picture): what was read from it, then the normal check. A picture that cannot be read well enough is not
    checked: the person is asked for a clearer one, or the text. The picture itself is dropped when this returns."""
    linked = bind_chat(chat_id)
    L = chat_lang(lang_hint)
    stop = _image_blocked(chat_id, len(data), L or "en", count=True)
    if stop:
        return [stop]
    try:
        reading = image.read_image(bytes(data), lang=L or "en")
        text = reading.text.strip()
        qr = [u for u in dict.fromkeys(reading.qr_urls) if u and u not in text]  # a link hidden in a QR code is checked like a written one
        R = L or (i18n.norm(reading.language) if reading.language else "en")  # the language to speak in when no check is made
        if not text and not qr:
            return [Reply(tr("I couldn't find any words in that picture. Please send a clearer one, or paste the text.", R))]
        head = tr("📷 I read this from your screenshot:", R)
        if not reading.legible:
            said = _read_reply(head, text, R, reading.sender, qr, reading.note)
            return [Reply((said + "\n\n" + tr("The picture was hard to read, so please check this matches what you see.", R) + "\n"
                           + tr("I haven't checked it yet. Please send a clearer picture, or paste the text.", R))[:4000])]
        origin = make_origin(channel=reading.channel, app=reading.app, sender=reading.sender, forwarded_from=forwarded_from)  # where the picture seems to come from
        result, checked = _checked(linked, "\n".join([t for t in (text, *qr) if t]), L, "screenshot", origin, chat_id)
        return [Reply(_read_reply(tr("📷 I read this from your screenshot:", result.lang), text, result.lang, reading.sender, qr, reading.note)), checked]
    except InputError as e:
        return [Reply(tr(e.message, L or "en"))]
    except Exception as e:  # a vision model that is down, a bug: never a stack trace in the chat
        note_failure("image", e)
        return [Reply(tr("Sorry, I couldn't read that. Please send the text.", L or "en"))]


def on_voice(chat_id: int, data: bytes, mime: str = "", lang_hint: str | None = None) -> list[Reply]:
    """A voice note (the bytes of the audio and its type, e.g. audio/ogg): what was heard, then the normal check. Dropped when this returns."""
    linked = bind_chat(chat_id)
    L = chat_lang(lang_hint)
    stop = _voice_blocked(chat_id, len(data), None, L or "en", count=True)
    if stop:
        return [stop]
    try:
        heard = audio.transcribe(bytes(data), mime=mime)
        text = heard.text.strip()
        R = L or (i18n.norm(heard.language) if heard.language else "en")
        if not text:
            return [Reply(tr("I couldn't hear any words in that voice note. Please try again, or send the text.", R))]
        result, checked = _checked(linked, text, L, "voice", chat_id=chat_id)
        return [Reply(_read_reply(tr("🎙️ I heard:", result.lang), text, result.lang)), checked]
    except InputError as e:
        return [Reply(tr(e.message, L or "en"))]
    except Exception as e:
        note_failure("voice", e)
        return [Reply(tr("Sorry, I couldn't read that. Please send the text.", L or "en"))]
