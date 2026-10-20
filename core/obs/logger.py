"""Structured JSONL event log with size-based rotation. Logging must NEVER break the app, so every failure is swallowed
(and counted). Privacy: callers pass hashes, lengths and enums, never message text."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import time

_lock = threading.Lock()
_SALT = secrets.token_hex(8)  # per-process: a hash is only good for spotting repeats within one run of the server
MAX_BYTES, KEEP = 5_000_000, 3
DROPPED = {"count": 0}


def log_dir() -> str:
    return os.getenv("BAITPROOF_LOG_DIR", "logs")


def path() -> str:
    return os.path.join(log_dir(), "events.jsonl")


def fingerprint(text: str) -> str:
    return hashlib.sha256((os.getenv("BAITPROOF_LOG_SALT") or _SALT).encode() + text.encode()).hexdigest()[:12]


def _rotate(p: str) -> None:
    for i in range(KEEP - 1, 0, -1):
        if os.path.exists(f"{p}.{i}"):
            os.replace(f"{p}.{i}", f"{p}.{i + 1}")
    os.replace(p, f"{p}.1")


def emit(event: dict) -> None:
    if not log_dir():
        return
    try:
        line = json.dumps({"ts": round(time.time(), 3), **event}, separators=(",", ":"), default=str)
        with _lock:
            os.makedirs(log_dir(), exist_ok=True)
            p = path()
            if os.path.exists(p) and os.path.getsize(p) > MAX_BYTES:
                _rotate(p)
            with open(p, "a", encoding="utf-8") as f:
                f.write(line + "\n")
    except Exception:
        DROPPED["count"] += 1
