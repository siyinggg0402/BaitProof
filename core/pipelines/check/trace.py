"""Gate-by-gate decision trace. Shown to the user ('How I decided'); the log keeps only stage/status/timing, never text."""
from __future__ import annotations

import time
from typing import Callable

from core.domain.schemas import TraceStep


class Trace:
    def __init__(self, on_event: Callable[[TraceStep], None] | None = None) -> None:
        self.steps: list[TraceStep] = []
        self._last = time.perf_counter()
        self._on_event = on_event  # the live stage view subscribes here

    def add(self, stage: str, status: str, detail: str) -> None:
        """status: pass | flag | skip | block"""
        now = time.perf_counter()
        step = TraceStep(stage=stage, status=status, detail=detail[:240], ms=int((now - self._last) * 1000))
        self._last = now
        self.steps.append(step)
        if self._on_event:
            try:
                self._on_event(step)
            except Exception:  # a broken listener must never break a check
                self._on_event = None
