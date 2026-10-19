"""Telegram bot logic, kept free of any Telegram import so it is unit-testable offline.
One shared engine (core/) behind both channels (PLAN §5). Each chat gets its own anonymous profile."""
from __future__ import annotations

import hashlib
import os

from core.domain.schemas import CheckResult, Verdict
from core.domain.tactics import TACTICS
from core.pipelines.check import check_message
from core.storage import db, model

WELCOME = ("Hi! I'm Baitproof 🛡️\n\nForward or paste any message you're unsure about and I'll tell you if it's a scam, "
           "show you the one giveaway, and add that trick to your practice.\n\n/score shows your Baitproof score.\n"
           "I keep the tricks I see, not your messages.")
ICON = {Verdict.SCAM: "🚨", Verdict.LIKELY_SCAM: "⚠️", Verdict.SAFE: "✅", Verdict.UNSURE: "❓", Verdict.VICTIM: "💛"}


def bind_chat(chat_id: int) -> None:
    """Anonymous per-chat profile. Only isolates users when BAITPROOF_MULTIUSER=1 (set it on any shared deploy)."""
    db.set_profile(hashlib.sha256(f"tg:{chat_id}".encode()).hexdigest()[:32])


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
    bind_chat(chat_id)
    if not text.strip():
        return "Send me the message you want checked."
    return format_result(check_message(text))


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
