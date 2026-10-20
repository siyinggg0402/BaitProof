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
from core.ai.prompts import grade_system, wwyd_system
from core.domain.i18n import norm, tactic_text, to_traditional, tr
from core.domain.lang import CJK, Z, to_simplified
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
# the same two checks for a reply written in Chinese (no word boundaries there; Z() makes each pattern match both scripts)
GOOD_ZH = Z("忽略|不理|无视|删除|拉黑|屏蔽|不要|不会|别|核实|核对|官方|报警|举报|挂断|打电话给(?:银行|警察|他|她|本人)|问问(?:家人|朋友|子女|孩子)")
BAD_ZH = Z("验证码是|我的密码|密码是|我会付|我来付|马上转|这就转|已经转|发给你|点了链接|点击了链接|照做")


# A distractor that describes a safe or reasonable action would make the quiz unfair. Deliberately specific: a scammer's
# framing ("click the link to verify your account") is a legitimately BAD option and must not be rejected.
SAFE_SOUNDING = re.compile(
    r"\b(?:ignore|delete|block|report|hang up|do nothing|nothing)\b"
    r"|\b(?:tell|ask|talk to|call|phone|contact|check with|confirm with|verify (?:with|through|by))\s+"
    r"(?:mom|mum|dad|someone|a (?:friend|family|trusted)|your|my|the (?:real|bank|police|company|official)|family|friends)\b"
    r"|\b(?:official|real) (?:website|number|site|app)\b", re.I)
SAFE_SOUNDING_ZH = Z("忽略|不理|无视|删除|拉黑|屏蔽|什么都不做|不做任何|不用理|报警|举报|挂断|"
                     "(?:告诉|问问|询问|联系|咨询)(?:家人|朋友|子女|孩子|儿女|银行|警察|本人)|打电话给(?:银行|警察|本人)|(?:官方|正规)(?:网站|电话|号码|客服|App)|核实")


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
    return [s.strip() for s in re.split(r"(?<=[.!?:])\s+|(?<=[。！？；])", text) if s.strip()]  # Chinese sentences end without a space after them


def localized(text: str, tactic: str, field: str, lang: str, safe: bool = False) -> str:
    """An explanation or next step in the reader's language. English: the text as written. Chinese: the text if it is already Chinese (converted to the
    reader's script); otherwise the trick's own plain-language one (`safe` messages have none, so they get the generic reassurance or nothing)."""
    lang = norm(lang)
    if lang == "en" or not text:
        return text or ""
    if CJK.search(text):
        return to_traditional(text) if lang == "zh-Hant" else to_simplified(text)
    if tr(text, lang) != text:  # a sentence we have translated (the generic "nothing here asks for money..." line)
        return tr(text, lang)
    return tactic_text(tactic, field, lang, TACTICS) if tactic in TACTICS and not safe else ""


def _pick_example(tactic: str, avoid: set[str], lang: str = "en") -> dict | None:
    pool = [e for e in library.all_examples(lang) if e.get("is_scam") and tactic in e["tactics"]]
    fresh = [e for e in pool if e["id"] not in avoid] or pool
    if not fresh:
        return None
    user = [e for e in fresh if e["source"] == "user"]
    return random.choice(user or fresh)


def _wrong_options(ex: dict, tactic: str, lang: str = "en") -> tuple[str, list[str]]:
    q = tr("What is the safest thing to do?", lang)
    if llm.available():
        try:
            out = llm.chat_json(wwyd_system(lang), f"MESSAGE: {ex['text']}\nSAFE ACTION: {ex['action']}", heavy=True, purpose="quiz-options")
            wrong = [str(o)[:140] for o in out.get("wrong_options", []) if o]
            wrong = [w for w in wrong if not SAFE_SOUNDING.search(w) and not SAFE_SOUNDING_ZH.search(w)][:3]
            if len(wrong) >= 2:  # keep the model's good options, top up from vetted templates if one was unfair
                spare = [tr(t, lang) for t in BAD_ACTIONS if t not in wrong]
                return str(out.get("question") or q)[:200], wrong + random.sample(spare, 3 - len(wrong))
        except llm.LLMUnavailable:
            pass
    return q, [tr(a, lang) for a in random.sample(BAD_ACTIONS, 3)]


def build_drill(tactic: str, reason: str, avoid: set[str] | None = None, lang: str = "en") -> Drill | None:
    ex = _pick_example(tactic, avoid or set(), lang)
    if not ex:
        return None
    formats = ["spot-trick", "what-to-do"]
    if ex.get("tell_phrase") and len(_sentences(ex["text"])) >= 3 and ex["tell_phrase"] in ex["text"]:
        formats.append("highlight-tell")
    if llm.available():
        formats.append("safe-reply")
    fmt = random.choice(formats)
    d = dict(id=uuid.uuid4().hex[:10], tactic=tactic, scenario=ex["text"], reason=tr(reason, lang),
             explanation=localized(ex["tell"], tactic, "tell", lang) or tactic_text(tactic, "tell", lang, TACTICS), tell_phrase=ex.get("tell_phrase", ""), format=fmt)
    action = localized(ex["action"], tactic, "action", lang) or tactic_text(tactic, "action", lang, TACTICS)
    if fmt == "spot-trick":
        others = random.sample([t for t in TACTICS if t not in ex["tactics"]], 3)
        opts = [tactic] + others
        random.shuffle(opts)
        return Drill(**d, question=tr("Which trick is this message using?", lang), options=[tactic_text(o, "label", lang, TACTICS) for o in opts],
                     correct_index=opts.index(tactic))
    if fmt == "highlight-tell":
        sents = _sentences(ex["text"])
        right = next(s for s in sents if ex["tell_phrase"] in s)
        wrong = random.sample([s for s in sents if s != right], min(3, len(sents) - 1))
        opts = [right] + wrong
        random.shuffle(opts)
        return Drill(**d, question=tr("Which part is the giveaway that this is a scam?", lang), options=opts, correct_index=opts.index(right))
    if fmt == "what-to-do":
        q, wrong = _wrong_options(ex, tactic, lang)
        opts = [action] + wrong
        random.shuffle(opts)
        return Drill(**d, question=q, options=opts, correct_index=opts.index(action))
    return Drill(**d, question=tr("Write a short, safe reply (or say what you would do).", lang), options=[], correct_index=None)


def build_session(n: int = 4, lang: str = "en") -> list[Drill]:
    drills: list[Drill] = []
    used: set[str] = set()
    for tactic, reason in select_tactics(n):
        d = build_drill(tactic, reason, used, lang)
        if d:
            used.add(d.scenario)
            drills.append(d)
    return drills


def _encourage(correct: bool, tell: str, lang: str = "en") -> str:
    return tr("Nice catch! {tell}", lang, tell=tell) if correct else tr("Good try. This trick is sneaky, and spotting it takes practice. The giveaway: {tell}", lang, tell=tell)


def grade(drill: Drill, choice: int | None = None, text: str = "", record: bool = True, lang: str = "en") -> Grade:
    if drill.correct_index is not None:
        ok = choice == drill.correct_index
        g = Grade(result="correct" if ok else "incorrect", note=_encourage(ok, drill.explanation, lang))
    else:
        g = _grade_free(drill, text.strip()[:500], lang)
    if record:
        model.record_result(drill.tactic, g.result)
    return g


def _grade_free(drill: Drill, text: str, lang: str = "en") -> Grade:
    if llm.available():
        try:
            out = llm.chat_json(grade_system(lang), f"SCAM MESSAGE: {drill.scenario}\nLEARNER REPLY: {text}", heavy=True, purpose="grade")
            if out.get("result") in ("correct", "partial", "incorrect"):
                return Grade(result=out["result"], note=str(out.get("note", ""))[:300] or drill.explanation)
        except llm.LLMUnavailable:
            pass
    if BAD_WORDS.search(text) or BAD_ZH.search(text) or not text:
        return Grade(result="incorrect", note=_encourage(False, drill.explanation, lang))
    if GOOD_WORDS.search(text) or GOOD_ZH.search(text):
        return Grade(result="correct", note=_encourage(True, drill.explanation, lang))
    return Grade(result="partial", note=tr("You're on the right track. Add that you'd check through an official number or website. ", lang) + drill.explanation)
