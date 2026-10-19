"""Nebius Token Factory client (OpenAI-compatible). All inference goes through here."""
from __future__ import annotations

import json
import os
import re


class LLMUnavailable(Exception):
    """No key configured, or the call/JSON failed. Callers must degrade, never crash."""


def available() -> bool:
    return bool(os.getenv("NEBIUS_API_KEY") and os.getenv("NEBIUS_BASE_URL") and os.getenv("NEBIUS_MODEL"))


def _client():
    from openai import OpenAI

    return OpenAI(base_url=os.environ["NEBIUS_BASE_URL"], api_key=os.environ["NEBIUS_API_KEY"], timeout=45)


def parse_json(raw: str) -> dict:
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.S)  # reasoning models
    raw = re.sub(r"```(?:json)?", "", raw)
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object")
    return json.loads(raw[start : end + 1])


def chat_json(system: str, user: str, heavy: bool = True, retries: int = 1) -> dict:
    if not available():
        raise LLMUnavailable("Nebius not configured")
    model = os.environ["NEBIUS_MODEL"] if heavy else os.getenv("NEBIUS_MODEL_LIGHT") or os.environ["NEBIUS_MODEL"]
    last: Exception | None = None
    for _ in range(retries + 1):
        try:
            resp = _client().chat.completions.create(
                model=model,
                temperature=0.2,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            )
            return parse_json(resp.choices[0].message.content or "")
        except Exception as e:  # network, auth, bad JSON: all degrade the same way
            last = e
    raise LLMUnavailable(str(last))
