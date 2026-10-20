"""Nebius Token Factory client (OpenAI-compatible). All inference goes through here."""
from __future__ import annotations

import json
import os
import re
import time

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


def available() -> bool:
    return bool(os.getenv("NEBIUS_API_KEY") and os.getenv("NEBIUS_BASE_URL") and os.getenv("NEBIUS_MODEL"))


def _client():
    from openai import OpenAI

    # Bounded worst case: 30s per attempt, one SDK retry (a cold start once took 47s on the first call; see warmup()).
    return OpenAI(base_url=os.environ["NEBIUS_BASE_URL"], api_key=os.environ["NEBIUS_API_KEY"], timeout=30, max_retries=1)


def parse_json(raw: str) -> dict:
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.S)  # reasoning models
    raw = re.sub(r"```(?:json)?", "", raw)
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object")
    return json.loads(raw[start : end + 1])


def chat_json(system: str, user: str, heavy: bool = True, retries: int = 1, purpose: str = "") -> dict:
    if not available():
        raise LLMUnavailable("Nebius not configured")
    model = os.environ["NEBIUS_MODEL"] if heavy else os.getenv("NEBIUS_MODEL_LIGHT") or os.environ["NEBIUS_MODEL"]
    global _flag_supported
    last: Exception | None = None
    for _ in range(retries + 1):
        t0 = time.perf_counter()
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
            USAGE["calls"] += 1
            tin = tout = 0
            if resp.usage:
                tin, tout = resp.usage.prompt_tokens or 0, resp.usage.completion_tokens or 0
                USAGE["prompt_tokens"] += tin
                USAGE["completion_tokens"] += tout
            parsed = parse_json(resp.choices[0].message.content or "")
            record_llm(purpose=purpose, model=model, ms=int((time.perf_counter() - t0) * 1000), tokens_in=tin, tokens_out=tout, ok=True)
            return parsed
        except Exception as e:  # network, auth, bad JSON: all degrade the same way
            last = e
            record_llm(purpose=purpose, model=model, ms=int((time.perf_counter() - t0) * 1000), ok=False,
                       error=f"{type(e).__name__} {getattr(e, 'status_code', '')}".strip())
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
