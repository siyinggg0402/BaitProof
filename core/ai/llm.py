"""Nebius Token Factory client (OpenAI-compatible). All inference goes through here."""
from __future__ import annotations

import base64
import json
import os
import re
import time

from core.domain.privacy import scrub_outgoing
from core.obs import record_llm


# Running totals so spend is visible and a budget can be enforced (scripts/eval_live.py).
USAGE = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0}
TEMPERATURE = float(os.getenv("BAITPROOF_TEMP", "0"))  # deterministic: the same message should get the same verdict
MAX_TOKENS = int(os.getenv("BAITPROOF_MAX_TOKENS", "2500"))  # per call
# Nemotron reasons silently for ~2k tokens before answering (slow, costly, and it truncated our JSON at 1.5k). Verdict
# quality doesn't need it, so thinking is OFF unless BAITPROOF_THINKING=1. Models that reject the flag are retried without it.
_THINKING = os.getenv("BAITPROOF_THINKING") == "1"
_flag_supported = True


class LLMUnavailable(Exception):
    """No key configured, or the call/JSON failed. Callers must degrade, never crash."""


# When the service keeps failing (a revoked key, credit used up, an outage), every stage of a check would try, wait and retry on its own, and one check could
# take a minute before it fell back to the rules. After BREAKER_FAILS failed calls in a row the model is skipped for BREAKER_PAUSE seconds (callers see the
# same LLMUnavailable they already handle); the next call after that is a trial, and one answer clears the count. A reply that is not valid JSON is the model's
# fault, not the service's, so it does not count.
BREAKER_FAILS, BREAKER_PAUSE = 3, float(os.getenv("BAITPROOF_BREAKER_PAUSE", "45"))  # 0 turns the pause off (a long evaluation run wants every call tried)
_breaker = {"fails": 0, "until": 0.0}


def available() -> bool:
    return bool(os.getenv("NEBIUS_API_KEY") and os.getenv("NEBIUS_BASE_URL") and os.getenv("NEBIUS_MODEL"))


def _client():
    from openai import OpenAI

    # Bounded worst case: 30s per attempt, one SDK retry (a cold start once took 47s on the first call; see warmup()).
    return OpenAI(base_url=os.environ["NEBIUS_BASE_URL"], api_key=os.environ["NEBIUS_API_KEY"], timeout=30, max_retries=1)


def _close(raw: str) -> str:
    """Add the brackets a model left off the end of its JSON (seen: a final '}' missing after a list of objects). Only ever appends closers."""
    stack, in_str, esc = [], False, False
    for c in raw:
        if in_str:
            esc = (c == "\\") and not esc
            if c == '"' and not esc:
                in_str = False
        elif c == '"':
            in_str = True
        elif c in "{[":
            stack.append("}" if c == "{" else "]")
        elif c in "}]" and stack:
            stack.pop()
    return raw + "".join(reversed(stack)) if not in_str else raw


def parse_json(raw: str, repair: bool = False) -> dict:
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.S)  # reasoning models
    raw = re.sub(r"```(?:json)?", "", raw)
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object")
    try:
        return json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        if not repair:
            raise
        return json.loads(_close(raw[start:end + 1]))


def chat_json(system: str, user: str, heavy: bool = True, retries: int = 1, purpose: str = "") -> dict:
    if not available():
        raise LLMUnavailable("Nebius not configured")
    model = os.environ["NEBIUS_MODEL"] if heavy else os.getenv("NEBIUS_MODEL_LIGHT") or os.environ["NEBIUS_MODEL"]
    user, scrubbed = scrub_outgoing(user)  # outgoing-data gate: callers already redact; this catches anything that slipped through
    global _flag_supported
    if time.monotonic() < _breaker["until"]:
        raise LLMUnavailable("paused after repeated failures")
    last: Exception | None = None
    for _ in range(retries + 1):
        t0 = time.perf_counter()
        reached = False  # did the service answer at all (even with text we cannot read)?
        try:
            extra = {} if _THINKING or not _flag_supported else {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
            try:
                resp = _client().chat.completions.create(
                    model=model, temperature=TEMPERATURE, max_tokens=MAX_TOKENS,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}], **extra)
            except Exception as e:
                if extra and getattr(e, "status_code", None) == 400:  # this model doesn't know the flag
                    _flag_supported = False
                    resp = _client().chat.completions.create(
                        model=model, temperature=TEMPERATURE, max_tokens=MAX_TOKENS,
                        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
                else:
                    raise
            reached = True
            _breaker["fails"] = 0
            USAGE["calls"] += 1
            tin = tout = 0
            if resp.usage:
                tin, tout = resp.usage.prompt_tokens or 0, resp.usage.completion_tokens or 0
                USAGE["prompt_tokens"] += tin
                USAGE["completion_tokens"] += tout
            parsed = parse_json(resp.choices[0].message.content or "")
            record_llm(purpose=purpose, model=model, ms=int((time.perf_counter() - t0) * 1000), tokens_in=tin, tokens_out=tout, ok=True, pii_scrubbed=scrubbed)
            return parsed
        except Exception as e:  # network, auth, bad JSON: all degrade the same way
            last = e
            record_llm(purpose=purpose, model=model, ms=int((time.perf_counter() - t0) * 1000), ok=False,
                       error=f"{type(e).__name__} {getattr(e, 'status_code', '')}".strip())
            if not reached:
                _breaker["fails"] += 1
                if _breaker["fails"] >= BREAKER_FAILS:
                    _breaker["until"] = time.monotonic() + BREAKER_PAUSE
                    break  # the rest of this call's attempts would only fail the same way
    raise LLMUnavailable(str(last))


# ---------------------------------------------------------------- vision (screenshots)
VISION_MODEL_DEFAULT = "nvidia/Nemotron-3.5-Super-VL"


def vision_available() -> bool:
    """True when a screenshot can be read: the AI is configured and BAITPROOF_VISION is not "0" (a switch for keeping images off the model)."""
    return available() and os.getenv("BAITPROOF_VISION", "1") != "0"


def _vision_client():
    """The same client with a shorter leash: a screenshot read takes 3-5 s, so a call that is still silent after 20 s is not going to answer. No SDK retry
    (vision_json makes its own single retry), so the worst case is two tries of 20 s, not four of 30 s. Test doubles without with_options are used as they are."""
    c = _client()
    return c.with_options(timeout=20, max_retries=0) if hasattr(c, "with_options") else c


def vision_json(system: str, user_text: str, images: list[tuple[str, bytes]], *, purpose: str = "vision", max_tokens: int = 900) -> dict:
    """Ask the vision model about one or more images and return its JSON answer. `images` is a list of (mime, bytes), e.g. ("image/png", data).

    PRIVACY: unlike text, an image cannot be scrubbed of personal data before it leaves (a screenshot shows names, phone numbers, avatars, account
    numbers), so scrub_outgoing() is applied to `user_text` only. The image is sent once, to the configured Nebius endpoint, and is never stored or
    logged here; the record we keep holds sizes, timing and token counts, never pixels or the transcript.

    Thinking is switched OFF (chat_template_kwargs.enable_thinking=False): measured on this model, without it the whole token budget goes on
    reasoning and the answer comes back empty; with it a screenshot read takes about 1-2 s and ~420 tokens. The answer carries a `_usage` entry
    ({"in", "out", "ms"}) that we set ourselves (never the model), so callers can log what the call cost.
    Raises LLMUnavailable when there is no key, the call fails, or the answer is not JSON."""
    if not vision_available():
        raise LLMUnavailable("Vision not configured")
    model = os.getenv("NEBIUS_MODEL_VISION") or VISION_MODEL_DEFAULT
    user_text, scrubbed = scrub_outgoing(user_text)
    parts: list[dict] = [{"type": "text", "text": user_text}]
    for mime, data in images:
        parts.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"}})
    messages = [{"role": "system", "content": system}, {"role": "user", "content": parts}]
    last: Exception | None = None
    for attempt in range(2):  # one retry: a vision call is not free, so no more than that
        t0 = time.perf_counter()
        try:
            kw = dict(model=model, temperature=0, max_tokens=max_tokens, messages=messages)
            try:
                resp = _vision_client().chat.completions.create(extra_body={"chat_template_kwargs": {"enable_thinking": False}}, **kw)
            except Exception as e:
                if getattr(e, "status_code", None) != 400:
                    raise
                resp = _vision_client().chat.completions.create(**kw)  # a model that does not know the flag
            USAGE["calls"] += 1
            tin = tout = 0
            if resp.usage:
                tin, tout = resp.usage.prompt_tokens or 0, resp.usage.completion_tokens or 0
                USAGE["prompt_tokens"] += tin
                USAGE["completion_tokens"] += tout
            ms = int((time.perf_counter() - t0) * 1000)
            parsed = parse_json(resp.choices[0].message.content or "", repair=True)
            record_llm(purpose=purpose, model=model, ms=ms, tokens_in=tin, tokens_out=tout, ok=True, pii_scrubbed=scrubbed)
            parsed["_usage"] = {"in": tin, "out": tout, "ms": ms}
            return parsed
        except Exception as e:
            last = e
            record_llm(purpose=purpose, model=model, ms=int((time.perf_counter() - t0) * 1000), ok=False,
                       error=f"{type(e).__name__} {getattr(e, 'status_code', '')}".strip())
            if getattr(e, "status_code", None) in (401, 403, 404):
                break  # a bad key or a missing model will not fix itself on a retry
    raise LLMUnavailable(str(last))


def warmup() -> None:
    """Fire one tiny call in the background so the first real user doesn't eat the model's cold start. Logged."""
    import threading

    from core.obs import emit

    def go():
        t0 = time.perf_counter()
        ok = True
        try:
            chat_json("Return ONLY JSON.", 'Return {"ok": true}', heavy=False, purpose="warmup")
        except LLMUnavailable:
            ok = False
        emit({"kind": "system", "event": "llm_warmup", "ok": ok, "ms": int((time.perf_counter() - t0) * 1000)})

    if available():
        threading.Thread(target=go, daemon=True).start()
