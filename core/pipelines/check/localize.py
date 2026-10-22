"""The reader gets the explanation in THEIR language. The analysis prompt deliberately does not carry a "reply language" instruction (measured: on
Chinese messages it made the model over-cautious), so the model writes its sentences in whatever language it likes, and for a Chinese reader that
was English in 12 of 12 live checks. This step fixes only the sentences the model wrote, in one tiny extra call, and only when they are not already
in the reader's script; if that call fails the caller falls back to the static, hand-written text."""
from __future__ import annotations

import json

from core.ai import llm
from core.ai.prompts import LOCALIZE_SYSTEM
from core.lang import i18n
from core.lang.text import CJK, to_simplified


def in_script(text: str, lang: str) -> bool:
    """Is this text already in the reader's language? Only Chinese needs checking: English is what the model writes by default."""
    return not text.strip() or i18n.norm(lang) == "en" or bool(CJK.search(text))


def convert_script(text: str, lang: str) -> str:
    """Chinese text in the wrong script (the model may write Traditional for a Simplified reader) is converted to the reader's."""
    if not CJK.search(text):
        return text
    return i18n.to_traditional(text) if i18n.norm(lang) == "zh-Hant" else (to_simplified(text) if i18n.norm(lang) == "zh" else text)


def translate(texts: list[str], lang: str) -> list[str] | None:
    """The same sentences in the reader's language, or None if the model is unavailable or answers badly (never a partial result)."""
    if not texts:
        return []
    try:
        out = llm.chat_json(LOCALIZE_SYSTEM, json.dumps({"language": i18n.PROMPT_NAMES[i18n.norm(lang)], "items": texts}, ensure_ascii=False), heavy=False, purpose="localize")
    except llm.LLMUnavailable:
        return None
    items = out.get("items") if isinstance(out, dict) else None
    if not isinstance(items, list) or len(items) != len(texts) or not all(isinstance(x, str) and CJK.search(x) for x in items):
        return None
    return [convert_script(x.strip(), lang) for x in items]


def explain_in(lang: str, tell: str, action: str, ledger) -> tuple[str, str]:
    """Put the model's giveaway, next step and per-trick reasons into the reader's language. A text that could not be translated is dropped (the
    giveaway and action become "" so the caller's static fallback applies; a trick's reason becomes the static 'The AI reviewer spotted: <trick>')."""
    from core.domain.tactics import TACTICS

    if i18n.norm(lang) == "en":
        return tell, action
    model_claims = [e for e in ledger.items if e.kind == "model" and e.supports == "scam" and e.source == "analysis" and e.claim]
    slots = [("tell", tell), ("action", action)] + [("claim", e.claim) for e in model_claims]
    wanted = [i for i, (_, t) in enumerate(slots) if not in_script(t, lang)]
    done = translate([slots[i][1] for i in wanted], lang) if wanted else []
    fixed = dict(zip(wanted, done)) if done is not None else {}
    result: list[str] = []
    for i, (_, t) in enumerate(slots):
        if i in wanted:
            result.append(fixed.get(i, ""))  # "" = could not translate
        else:
            result.append(convert_script(t, lang))
    tell, action = result[0], result[1]
    for e, text in zip(model_claims, result[2:]):
        e.claim = text or i18n.tr("The AI reviewer spotted: {label}", lang, label=i18n.tactic_text(e.tactic, "label", lang, TACTICS).lower() if e.tactic else "")
    return tell, action
