"""Train pipeline (PLAN §6c): select tactics -> build drills from real/seed examples -> grade -> update model."""
from __future__ import annotations

import random
import re
import uuid
from datetime import timedelta

from core.storage import db
from core.storage import library
from core.ai import llm
from core.storage import model
from core.ai.prompts import GRADE_SYSTEM, WWYD_SYSTEM
from core.domain.schemas import Drill, Grade
from core.domain.tactics import TACTICS

BAD_ACTIONS = [
    "Click the link to check if it's real",
    "Reply with the details they asked for, to be safe",
    "Do what they say quickly so nothing bad happens",
    "Call the phone number written in the message",
    "Send a small amount first to see if it works",
    "Forward it to friends and ask what to do, then follow the link",
]
GOOD_WORDS = re.compile(r"\b(?:ignore|delete|block|don'?t|do not|never|verify|call (?:the )?(?:bank|them|my)|official|real (?:site|website|number)|report|hang up|won'?t)\b", re.I)
BAD_WORDS = re.compile(r"\b(?:here is|my code|my password|i will pay|i'll pay|sending|click(?:ed)? the link)\b", re.I)


# A distractor that describes a safe or reasonable action would make the quiz unfair. Deliberately specific: a scammer's
# framing ("click the link to verify your account") is a legitimately BAD option and must not be rejected.
SAFE_SOUNDING = re.compile(
    r"\b(?:ignore|delete|block|report|hang up|do nothing|nothing)\b"
    r"|\b(?:tell|ask|talk to|call|phone|contact|check with|confirm with|verify (?:with|through|by))\s+"
    r"(?:mom|mum|dad|someone|a (?:friend|family|trusted)|your|my|the (?:real|bank|police|company|official)|family|friends)\b"
    r"|\b(?:official|real) (?:website|number|site|app)\b", re.I)


def select_tactics(n: int = 4) -> list[tuple[str, str]]:
    """Weakest + due + recently seen in REAL life. Returns [(tactic, reason)]."""
    now = db.now()
    base = {"untested": 1.5, "weak": 3.0, "learning": 1.5, "strong": 0.3}
    scored = []
    for r in model.all_mastery():
        s, reason = base[r["level"]], "keep practising"
        if r["level"] == "untested":
            reason = "not yet tested"
        if r["level"] == "weak":
            reason = "you missed this one before" if r["fail"] else "this is a weak spot"
        due = db.parse(r["due"])
        if due and due <= now and r["level"] != "untested":
            s, reason = s + 2, "time to review it" if r["level"] != "weak" else reason
        seen = db.parse(r["last_seen"])
        if seen and now - seen < timedelta(days=3):
            s, reason = s + 3 + min(r["exposure"], 3) * 0.3, "you just got a scam like this"
        scored.append((s + random.random() * 0.5, r["tactic"], reason))
    scored.sort(reverse=True)
    return [(t, why) for _, t, why in scored[:n]]


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?:])\s+", text) if s.strip()]


def _pick_example(tactic: str, avoid: set[str]) -> dict | None:
    pool = [e for e in library.all_examples() if e.get("is_scam") and tactic in e["tactics"]]
    fresh = [e for e in pool if e["id"] not in avoid] or pool
    if not fresh:
        return None
    user = [e for e in fresh if e["source"] == "user"]
    return random.choice(user or fresh)


def _wrong_options(ex: dict, tactic: str) -> tuple[str, list[str]]:
    q = "What is the safest thing to do?"
    if llm.available():
        try:
            out = llm.chat_json(WWYD_SYSTEM, f"MESSAGE: {ex['text']}\nSAFE ACTION: {ex['action']}", heavy=True)
            wrong = [str(o)[:140] for o in out.get("wrong_options", []) if o]
            wrong = [w for w in wrong if not SAFE_SOUNDING.search(w)][:3]
            if len(wrong) >= 2:  # keep the model's good options, top up from vetted templates if one was unfair
                spare = [t for t in BAD_ACTIONS if t not in wrong]
                return str(out.get("question") or q)[:200], wrong + random.sample(spare, 3 - len(wrong))
        except llm.LLMUnavailable:
            pass
    return q, random.sample(BAD_ACTIONS, 3)


def build_drill(tactic: str, reason: str, avoid: set[str] | None = None) -> Drill | None:
    ex = _pick_example(tactic, avoid or set())
    if not ex:
        return None
    formats = ["spot-trick", "what-to-do"]
    if ex.get("tell_phrase") and len(_sentences(ex["text"])) >= 3 and ex["tell_phrase"] in ex["text"]:
        formats.append("highlight-tell")
    if llm.available():
        formats.append("safe-reply")
    fmt = random.choice(formats)
    d = dict(id=uuid.uuid4().hex[:10], tactic=tactic, scenario=ex["text"], reason=reason,
             explanation=ex["tell"] or TACTICS[tactic]["tell"], tell_phrase=ex.get("tell_phrase", ""), format=fmt)
    action = ex["action"] or TACTICS[tactic]["action"]
    if fmt == "spot-trick":
        others = random.sample([t for t in TACTICS if t not in ex["tactics"]], 3)
        opts = [tactic] + others
        random.shuffle(opts)
        return Drill(**d, question="Which trick is this message using?", options=[TACTICS[o]["label"] for o in opts],
                     correct_index=opts.index(tactic))
    if fmt == "highlight-tell":
        sents = _sentences(ex["text"])
        right = next(s for s in sents if ex["tell_phrase"] in s)
        wrong = random.sample([s for s in sents if s != right], min(3, len(sents) - 1))
        opts = [right] + wrong
        random.shuffle(opts)
        return Drill(**d, question="Which part is the giveaway that this is a scam?", options=opts, correct_index=opts.index(right))
    if fmt == "what-to-do":
        q, wrong = _wrong_options(ex, tactic)
        opts = [action] + wrong
        random.shuffle(opts)
        return Drill(**d, question=q, options=opts, correct_index=opts.index(action))
    return Drill(**d, question="Write a short, safe reply (or say what you would do).", options=[], correct_index=None)


def build_session(n: int = 4) -> list[Drill]:
    drills: list[Drill] = []
    used: set[str] = set()
    for tactic, reason in select_tactics(n):
        d = build_drill(tactic, reason, used)
        if d:
            used.add(d.scenario)
            drills.append(d)
    return drills


def _encourage(correct: bool, tell: str) -> str:
    return f"Nice catch! {tell}" if correct else f"Good try. This trick is sneaky, and spotting it takes practice. The giveaway: {tell}"


def grade(drill: Drill, choice: int | None = None, text: str = "", record: bool = True) -> Grade:
    if drill.correct_index is not None:
        ok = choice == drill.correct_index
        g = Grade(result="correct" if ok else "incorrect", note=_encourage(ok, drill.explanation))
    else:
        g = _grade_free(drill, text.strip()[:500])
    if record:
        model.record_result(drill.tactic, g.result)
    return g


def _grade_free(drill: Drill, text: str) -> Grade:
    if llm.available():
        try:
            out = llm.chat_json(GRADE_SYSTEM, f"SCAM MESSAGE: {drill.scenario}\nLEARNER REPLY: {text}", heavy=True)
            if out.get("result") in ("correct", "partial", "incorrect"):
                return Grade(result=out["result"], note=str(out.get("note", ""))[:300] or drill.explanation)
        except llm.LLMUnavailable:
            pass
    if BAD_WORDS.search(text) or not text:
        return Grade(result="incorrect", note=_encourage(False, drill.explanation))
    if GOOD_WORDS.search(text):
        return Grade(result="correct", note=_encourage(True, drill.explanation))
    return Grade(result="partial", note="You're on the right track. Add that you'd check through an official number or website. " + drill.explanation)
