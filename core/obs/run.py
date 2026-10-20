"""A Run is everything we want to know about one check: stages, tool calls, model calls. Lives in a ContextVar so
deep code (llm.py, tools) can record into it without threading a handle through every function."""
from __future__ import annotations

import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class Run:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    t0: float = field(default_factory=time.perf_counter)
    tools: list[dict] = field(default_factory=list)  # {tool, ok, ms, error?}
    llm: list[dict] = field(default_factory=list)  # {purpose, model, ms, tokens_in, tokens_out, ok, error?}
    rounds: int = 1
    meta: dict = field(default_factory=dict)  # language, etc.: enums and numbers only

    @property
    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.t0) * 1000)

    def llm_totals(self) -> dict:
        return {"calls": len(self.llm), "ok": sum(1 for c in self.llm if c["ok"]),
                "tokens_in": sum(c.get("tokens_in", 0) for c in self.llm), "tokens_out": sum(c.get("tokens_out", 0) for c in self.llm)}


_current: ContextVar[Run | None] = ContextVar("bp_run", default=None)


def start() -> Run:
    r = Run()
    _current.set(r)
    return r


def current() -> Run | None:
    return _current.get()


def record_llm(**kw) -> None:
    if (r := current()) is not None:
        r.llm.append(kw)


def record_tool(**kw) -> None:
    if (r := current()) is not None:
        r.tools.append(kw)
