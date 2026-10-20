"""Telegram bot logic, kept free of any Telegram import so it is unit-testable offline.
One shared engine (core/) behind both channels (PLAN §5). Each chat gets its own anonymous profile."""
from __future__ import annotations

import hashlib
import os

from core.domain.schemas import CheckResult, Verdict
from core.domain.tactics import TACTICS
from core.pipelines.check import check_message
from core.storage import db, history, links, model

WELCOME = ("Hi! I'm Baitproof 🛡️\n\nForward or paste any message you're unsure about and I'll tell you if it's a scam, "
           "show you the one giveaway, and add that trick to your practice.\n\n"
           "/link CODE connects this chat to your Baitproof web profile, so everything you check here shows up in your records.\n"
           "/history shows your latest checks, /score your Baitproof score, /unlink disconnects.\n"
           "I keep the tricks I see, not your messages.")
ICON = {Verdict.SCAM: "🚨", Verdict.LIKELY_SCAM: "⚠️", Verdict.SAFE: "✅", Verdict.UNSURE: "❓", Verdict.VICTIM: "💛"}


def bind_chat(chat_id: int) -> bool:
    """Point storage at this chat's profile. A LINKED chat uses the web profile it was linked to (same records, practice and score);
    an unlinked one gets its own anonymous profile. Returns True if linked. Isolation needs BAITPROOF_MULTIUSER=1 on a shared deploy."""
    linked = links.profile_for_chat(chat_id)
    db.set_profile(linked if linked else hashlib.sha256(f"tg:{chat_id}".encode()).hexdigest()[:32])  # 'local' is not a valid id: stays on the default DB
    return linked is not None


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
    lines = [r.headline]
    if r.tell:
        lines += ["", f"The giveaway: {r.tell}"]
    if r.action:
        lines += ["", f"What to do: {r.action}"]
    if r.added_to_training:
        lines += ["", "📚 Added to your practice: " + ", ".join(TACTICS[t]["label"] for t in r.added_to_training)]
    return "\n".join(lines)[:4000]


def on_text(chat_id: int, text: str) -> str:
    linked = bind_chat(chat_id)
    if not text.strip():
        return "Send me the message you want checked."
    result = check_message(text)
    history.add(result, "telegram", text)  # the record: verdict, tricks, giveaway and a short redacted preview, never the raw message
    out = format_result(result)
    if linked and web_url():
        out += f"\n\n🗂 Saved to your records: {web_url('/records')}"
    return out[:4000]


def on_start(chat_id: int, payload: str = "") -> str:
    """/start, optionally with a link code (the web page offers a one-tap t.me link that carries it)."""
    return on_link(chat_id, payload) if payload.strip() else WELCOME


def on_link(chat_id: int, code: str) -> str:
    if not code.strip():
        return "Send /link followed by the 6-character code from the Records page on Baitproof, for example /link K7M2QX."
    if _too_many_attempts(chat_id):
        return "Too many tries. Please wait a few minutes and get a fresh code from the website."
    profile = links.redeem(code, chat_id)
    if profile is None:
        return "That code didn't work. It may have expired (they last 10 minutes) or been used already. Get a fresh one from the Records page."
    bind_chat(chat_id)
    return ("✅ Linked! Everything you check here now shows up in your Baitproof records, and the tricks you meet go into your practice."
            + (f"\n\nSee them: {web_url('/records')}" if web_url() else ""))


def on_unlink(chat_id: int) -> str:
    return "Disconnected. Your records stay in your Baitproof profile." if links.unlink_chat(chat_id) else "This chat wasn't linked."


def on_history(chat_id: int, n: int = 5) -> str:
    bind_chat(chat_id)
    rows = history.list_checks(n)
    if not rows:
        return "No checks yet. Paste or forward a message and I'll check it."
    lines = ["Your latest checks:"]
    for r in rows:
        tricks = ", ".join(TACTICS[t]["label"] for t in r["tactics"] if t in TACTICS)
        lines.append(f"{ICON.get(Verdict(r['verdict']), '•')} {r['ts'][:10]} via {r['channel']}: " + (r["preview"] or r["headline"])[:70] + (f" ({tricks})" if tricks else ""))
    return "\n".join(lines) + (f"\n\nAll of them: {web_url('/records')}" if web_url() else "")


def on_score(chat_id: int) -> str:
    bind_chat(chat_id)
    m = model.resilience_map()
    weak = [t["label"] for t in m["tactics"] if t["level"] == "weak"]
    out = f"Your Baitproof score: {m['score']}/100"
    if weak:
        out += "\nWeakest tricks: " + ", ".join(weak)
    if m["due"]:
        out += f"\n{m['due']} trick(s) due for a refresher."
    url = os.getenv("BAITPROOF_URL")
    return out + (f"\n\nPractise here: {url}/train" if url else "")


def nudge_text(chat_id: int) -> str | None:
    """Daily nudge: only when something is actually due, so it never becomes noise."""
    bind_chat(chat_id)
    m = model.resilience_map()
    if not m["due"]:
        return None
    url = os.getenv("BAITPROOF_URL", "")
    return f"🛡️ {m['due']} scam trick(s) are due for a one-minute refresher." + (f" {url}/train" if url else "")
